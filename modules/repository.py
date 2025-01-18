import httpx
import logging
import asyncio
import time
from typing import Dict, List, Optional, Union
from uuid import UUID
from datetime import datetime
from urllib.parse import urlparse
from config.settings import settings
from typing import TypedDict, Literal
from .metrics import Metrics
from .base import AsyncHTTPClient
from .validation import validate_input
from .logging_utils import log_request_response
from database.connection import get_db_connection
from .types import RepositoryStatus, APIResponse, SearchType
from .exceptions import APIError, DatabaseError, ValidationError

class RepositoryManager(AsyncHTTPClient):
    def __init__(self, base_url: str = settings.API_BASE_URL, timeout: float = settings.timeout.connect_timeout):
        super().__init__(base_url, timeout)
        self._cleanup_tasks = []
        self.metrics = Metrics()
        self.cache = RepositoryCache()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Clean up any pending tasks
        for task in self._cleanup_tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*self._cleanup_tasks, return_exceptions=True)
        await self.client.aclose()

    def validate_repository_url(self, url: str) -> bool:
        """Validate repository URL format"""
        try:
            parsed = urlparse(url)
            if not all([parsed.scheme, parsed.netloc]):
                raise ValidationError("Invalid repository URL format")
            if parsed.scheme not in ('http', 'https', 'git'):
                raise ValidationError("Unsupported repository URL scheme")
            return True
        except Exception as e:
            raise ValidationError(f"URL validation error: {str(e)}")

    async def _make_request_with_retry(self, method: str, endpoint: str, **kwargs) -> httpx.Response:
        """Make HTTP request with retry logic"""
        retry_count = 0
        while retry_count < settings.retry.max_retries:
            try:
                response = await getattr(self.client, method)(endpoint, **kwargs)
                response.raise_for_status()
                return response
            except httpx.HTTPError as e:
                retry_count += 1
                if retry_count == settings.retry.max_retries:
                    raise APIError(f"HTTP error after {retry_count} retries: {str(e)}")
                await asyncio.sleep(settings.retry.retry_delay * (settings.retry.retry_backoff ** retry_count))

    async def add_repository(
        self, 
        url: str, 
        branch: Optional[str] = None,
        auth_token: Optional[str] = None
    ) -> APIResponse:
        async with self.metrics.timer("repository_add_duration"):
            try:
                # Input validation
                validate_input({
                    "url": url,
                    "branch": branch,
                    "auth_token": auth_token
                }, {
                    "url": str,
                    "branch": Optional[str],
                    "auth_token": Optional[str]
                })
                
                # Validate URL format
                self.validate_repository_url(url)
                
                # Track metrics
                await self.metrics.increment("repository_add_attempts")
                
                request_data = {
                    "repository_url": url,
                    "branch": branch,
                    "auth_token": auth_token
                }
                
                # Log request
                await log_request_response(request_data, None)
                
                try:
                    # Make API request with retry logic
                    async with get_db_connection() as conn:
                        async with conn.transaction():
                            # API call
                            response = await self._make_request_with_retry(
                                "post", 
                                "/add",
                                json=request_data,
                                timeout=30.0
                            )
                            response_data = response.json()
                            
                            # Log response
                            await log_request_response(request_data, response_data)
                            
                            # Insert into database
                            await conn.execute("""
                                INSERT INTO repositories (
                                    dataset_id, url, branch, status, last_sync
                                ) VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP)
                            """, (
                                str(response_data['dataset_id']),
                                url,
                                branch,
                                response_data['status']
                            ))
                            
                            # Record success metric
                            await self.metrics.increment("repository_add_success")
                            
                            return APIResponse(
                                status="success",
                                message="Repository added successfully",
                                data={
                                    "dataset_id": str(response_data['dataset_id']),
                                    "status": response_data['status']
                                }
                            )
                            
                except httpx.HTTPError as e:
                    await self.metrics.increment("repository_add_api_errors")
                    logging.error(f"HTTP error adding repository: {str(e)}")
                    return APIResponse(
                        status="error", 
                        message="API error",
                        errors=[str(e)]
                    )
                    
                except DatabaseError as e:
                    await self.metrics.increment("repository_db_errors")
                    logging.error(f"Database error adding repository: {str(e)}")
                    return APIResponse(
                        status="error",
                        message="Database error",
                        errors=[str(e)]
                    )
                    
            except ValidationError as e:
                await self.metrics.increment("repository_validation_errors")
                logging.error(f"Validation error: {str(e)}")
                return APIResponse(
                    status="error",
                    message="Validation error", 
                    errors=[str(e)]
                )
                
            except Exception as e:
                await self.metrics.increment("repository_add_errors")
                logging.error(f"Unexpected error: {str(e)}")
                return APIResponse(
                    status="error",
                    message="An unexpected error occurred",
                    errors=[str(e)]
                )

    async def batch_add_repositories(self, repositories: List[Dict[str, str]]) -> List[APIResponse]:
        """Add multiple repositories in batch"""
        results = []
        for repo in repositories:
            try:
                result = await self.add_repository(
                    url=repo['url'],
                    branch=repo.get('branch'),
                    auth_token=repo.get('auth_token')
                )
                results.append(result)
            except ValidationError as e:
                await self.metrics.increment("repository_batch_validation_errors")
                results.append(APIResponse(status="error", message=f"Validation error: {str(e)}"))
            except APIError as e:
                await self.metrics.increment("repository_batch_api_errors")
                results.append(APIResponse(status="error", message=f"API error: {str(e)}"))
            except DatabaseError as e:
                await self.metrics.increment("repository_batch_db_errors")
                results.append(APIResponse(status="error", message=f"Database error: {str(e)}"))
        return results

    async def get_repositories_status(self) -> List[Dict]:
        """Get status of all repositories"""
        response = await self.client.get("/datasets/status")
        return response.json()["repositories"]

    async def delete_repository(self, dataset_id: UUID) -> Dict:
        """Delete a repository"""
        try:
            # Track metrics
            await self.metrics.increment("repository_delete_attempts")
            start_time = time.time()
            
            # Log request
            request_data = {"dataset_id": str(dataset_id)}
            await log_request_response(request_data, None)
            
            try:
                # API call
                response = await self.client.delete(f"/datasets/{dataset_id}")
                response.raise_for_status()
                
                # Log response
                await log_request_response(request_data, response.json())
                
                # Local DB operation
                with get_db_connection() as conn:
                    conn.execute("DELETE FROM repositories WHERE dataset_id = ?", 
                            (str(dataset_id),))
                    conn.commit()
                    
                # Record success and timing
                await self.metrics.increment("repository_delete_success")
                await self.metrics.record_time("repository_delete_duration", time.time() - start_time)
                
                return response.json()
                
            except httpx.HTTPError as e:
                await self.metrics.increment("repository_delete_api_errors")
                logging.error(f"HTTP error deleting repository: {str(e)}")
                raise
            except Exception as e:
                await self.metrics.increment("repository_delete_errors")
                logging.error(f"Error deleting repository: {str(e)}")
                raise
                
        except Exception as e:
            await self.metrics.increment("repository_delete_errors")
            logging.error(f"Error in delete_repository: {str(e)}")
            raise

    async def sync_repository(self, dataset_id: UUID) -> Dict:
        """Trigger repository sync"""
        try:
            # Track metrics
            await self.metrics.increment("repository_sync_attempts")
            start_time = time.time()
            
            request_data = {"dataset_id": str(dataset_id)}
            await log_request_response(request_data, None)
            
            try:
                response = await self.client.post("/cognify", json=request_data)
                response.raise_for_status()
                
                # Log response
                await log_request_response(request_data, response.json())
                
                with get_db_connection() as conn:
                    conn.execute("""
                        UPDATE repositories 
                        SET status = 'syncing', last_sync = CURRENT_TIMESTAMP 
                        WHERE dataset_id = ?
                    """, (str(dataset_id),))
                    conn.commit()
                
                # Record success and timing
                await self.metrics.increment("repository_sync_success")
                await self.metrics.record_time("repository_sync_duration", time.time() - start_time)
                
                return response.json()
                
            except Exception as e:
                await self.metrics.increment("repository_sync_errors")
                logging.error(f"Error syncing repository: {str(e)}")
                raise
                
        except Exception as e:
            await self.metrics.increment("repository_sync_errors")
            logging.error(f"Error in sync_repository: {str(e)}")
            raise

    async def process_repository(self, dataset_id: Optional[UUID] = None) -> Dict:
        """Process a repository or all repositories"""
        try:
            # Input validation
            if dataset_id:
                validate_input({"dataset_id": dataset_id}, {"dataset_id": UUID})

            # Track metrics
            await self.metrics.increment("repository_process_attempts")
            start_time = time.time()

            request_data = {
                "dataset_id": str(dataset_id) if dataset_id else None
            }

            # Log request
            await log_request_response(request_data, None)

            try:
                response = await self.client.post("/cognify", json=request_data)
                response.raise_for_status()

                # Log response
                await log_request_response(request_data, response.json())

                # Record success and timing
                await self.metrics.increment("repository_process_success")
                await self.metrics.record_time("repository_process_duration", time.time() - start_time)

                return response.json()

            except httpx.HTTPError as e:
                await self.metrics.increment("repository_process_api_errors")
                logging.error(f"HTTP error processing repository: {str(e)}")
                raise APIError(f"HTTP error processing repository: {str(e)}")

        except Exception as e:
            await self.metrics.increment("repository_process_errors")
            logging.error(f"Error in process_repository: {str(e)}")
            raise

    async def prune_data(self) -> Dict[str, str]:
        """Prune repository data"""
        try:
            # Track metrics
            await self.metrics.increment("data_prune_attempts")
            start_time = time.time()

            # Log request
            await log_request_response({"action": "prune_data"}, None)

            try:
                response = await self.client.post("/prune/data")
                response.raise_for_status()

                # Log response
                await log_request_response({"action": "prune_data"}, response.json())

                # Record success and timing
                await self.metrics.increment("data_prune_success")
                await self.metrics.record_time("data_prune_duration", time.time() - start_time)

                return response.json()

            except httpx.HTTPError as e:
                await self.metrics.increment("data_prune_api_errors")
                logging.error(f"HTTP error pruning data: {str(e)}")
                raise APIError(f"HTTP error pruning data: {str(e)}")

        except Exception as e:
            await self.metrics.increment("data_prune_errors")
            logging.error(f"Error in prune_data: {str(e)}")
            raise

    async def prune_system(self, metadata: bool = False, 
                        graph: bool = False, 
                        vector: bool = False) -> Dict[str, str]:
        """Prune system data"""
        try:
            # Input validation
            validate_input({
                "metadata": metadata,
                "graph": graph,
                "vector": vector
            }, {
                "metadata": bool,
                "graph": bool,
                "vector": bool
            })

            # Track metrics
            await self.metrics.increment("system_prune_attempts")
            start_time = time.time()

            request_data = {
                "metadata": metadata,
                "graph": graph,
                "vector": vector
            }

            # Log request
            await log_request_response(request_data, None)

            try:
                response = await self.client.post("/prune/system", json=request_data)
                response.raise_for_status()

                # Log response
                await log_request_response(request_data, response.json())

                # Record success and timing
                await self.metrics.increment("system_prune_success")
                await self.metrics.record_time("system_prune_duration", time.time() - start_time)

                return response.json()

            except httpx.HTTPError as e:
                await self.metrics.increment("system_prune_api_errors")
                logging.error(f"HTTP error pruning system: {str(e)}")
                raise APIError(f"HTTP error pruning system: {str(e)}")

        except Exception as e:
            await self.metrics.increment("system_prune_errors")
            logging.error(f"Error in prune_system: {str(e)}")
            raise

    async def toggle_repository_state(self, dataset_id: UUID, active: bool) -> Dict:
        """Toggle repository active state"""
        try:
            # Input validation
            validate_input({
                "dataset_id": dataset_id,
                "active": active
            }, {
                "dataset_id": UUID,
                "active": bool
            })

            # Track metrics
            await self.metrics.increment("repository_state_toggle_attempts")
            start_time = time.time()

            request_data = {
                "dataset_id": str(dataset_id),
                "active": active
            }

            # Log request
            await log_request_response(request_data, None)

            try:
                with get_db_connection() as conn:
                    conn.execute("""
                        UPDATE repositories 
                        SET is_active = ?, status = ?
                        WHERE dataset_id = ?
                    """, (active, "active" if active else "inactive", str(dataset_id)))
                    conn.commit()

                response_data = {
                    "status": "success",
                    "message": f"Repository state updated to {'active' if active else 'inactive'}"
                }

                # Log response
                await log_request_response(request_data, response_data)

                # Record success and timing
                await self.metrics.increment("repository_state_toggle_success")
                await self.metrics.record_time("repository_state_toggle_duration", time.time() - start_time)

                return response_data

            except Exception as e:
                await self.metrics.increment("repository_state_toggle_db_errors")
                logging.error(f"Database error toggling repository state: {str(e)}")
                raise DatabaseError(f"Error toggling repository state: {str(e)}")

        except Exception as e:
            await self.metrics.increment("repository_state_toggle_errors")
            logging.error(f"Error in toggle_repository_state: {str(e)}")
            raise
    
    async def batch_add_repositories(self, repositories: List[Dict[str, str]]) -> List[APIResponse]:
        """Add multiple repositories in batch"""
        futures = []
        for repo in repositories:
            futures.append(self.request_batcher.add_request({
                "url": repo['url'],
                "branch": repo.get('branch'),
                "auth_token": repo.get('auth_token')
            }))
        
        return await asyncio.gather(*futures)


class RepositoryCache:
    def __init__(self, cache_duration: int = 300):  # 5 minutes default
        self._cache = {}
        self._cache_duration = cache_duration
        self._lock = asyncio.Lock()

    async def get(self, dataset_id: UUID) -> Optional[Dict]:
        async with self._lock:
            if dataset_id in self._cache:
                entry = self._cache[dataset_id]
                if time.time() - entry['timestamp'] < self._cache_duration:
                    return entry['data']
                del self._cache[dataset_id]
            return None

    async def set(self, dataset_id: UUID, data: Dict):
        async with self._lock:
            self._cache[dataset_id] = {
                'data': data,
                'timestamp': time.time()
            }

    async def invalidate(self, dataset_id: UUID):
        async with self._lock:
            self._cache.pop(dataset_id, None)

    async def clear(self):
        async with self._lock:
            self._cache.clear()