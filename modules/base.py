import httpx
from typing import AsyncContextManager, Type, Dict
from pydantic import BaseModel
from collections import defaultdict
import asyncio

class AsyncHTTPClient(AsyncContextManager):
    def __init__(self, base_url: str, timeout: float = 30.0, max_retries: int = 3):
        self.max_retries = max_retries
        self.retry_delay = 1.0
        self.client = httpx.AsyncClient(
            base_url=str(base_url),
            timeout=timeout,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
        )

    async def _request_with_retry(self, method: str, url: str, **kwargs):
        for attempt in range(self.max_retries):
            try:
                response = await getattr(self.client, method)(url, **kwargs)
                response.raise_for_status()
                return response
            except httpx.HTTPError as e:
                if attempt == self.max_retries - 1:
                    raise APIError(f"HTTP request failed after {self.max_retries} attempts: {str(e)}")
                await asyncio.sleep(self.retry_delay * (2 ** attempt))
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

class RequestBatcher:
    def __init__(self, batch_size: int = 5, batch_window: float = 0.1):
        self.batch_size = batch_size
        self.batch_window = batch_window
        self.pending_requests = []
        self.lock = asyncio.Lock()
        self._batch_task = None

    async def add_request(self, request: Dict) -> asyncio.Future:
        future = asyncio.Future()
        
        async with self.lock:
            self.pending_requests.append((request, future))
            
            if len(self.pending_requests) >= self.batch_size:
                if self._batch_task:
                    self._batch_task.cancel()
                self._batch_task = asyncio.create_task(self._process_batch())
            elif not self._batch_task:
                self._batch_task = asyncio.create_task(self._process_batch())
        
        return await future

    async def _process_batch(self):
        await asyncio.sleep(self.batch_window)
        
        async with self.lock:
            if not self.pending_requests:
                return
                
            batch = self.pending_requests[:self.batch_size]
            self.pending_requests = self.pending_requests[self.batch_size:]
            self._batch_task = None

        try:
            # Process the batch
            results = await self._execute_batch([req for req, _ in batch])
            
            # Set results for futures
            for (_, future), result in zip(batch, results):
                if not future.done():
                    future.set_result(result)
                    
        except Exception as e:
            # Handle errors
            for _, future in batch:
                if not future.done():
                    future.set_exception(e)