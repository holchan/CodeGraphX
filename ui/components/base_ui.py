from typing import Callable, Any, List
import gradio as gr
from gradio.components import Component
from functools import wraps
import logging
import json
from datetime import datetime
from uuid import uuid4
import asyncio
from collections import defaultdict
from typing import Dict, Type
from pydantic import BaseModel
from modules.exceptions import ValidationError

def with_error_boundary(func: Callable) -> Callable:
    @wraps(func)
    async def wrapper(*args, **kwargs) -> Any:
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logging.error(f"Error in {func.__name__}: {str(e)}")
            gr.Error(f"An error occurred: {str(e)}")
            return None
    return wrapper

def with_loading_state(components: List[Component]):
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            for component in components:
                component.interactive = False
            try:
                return await func(*args, **kwargs)
            finally:
                for component in components:
                    component.interactive = True
        return wrapper
    return decorator

def validate_input(data: Dict[str, Any], schema: Type[BaseModel]) -> Dict[str, Any]:
    try:
        validated = schema.parse_obj(data)
        return validated.dict()
    except ValidationError as e:
        raise ValidationError(f"Input validation failed: {str(e)}")

async def log_request_response(request: Dict[str, Any], response: Dict[str, Any]):
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "request_id": str(uuid4()),
        "request": request,
        "response": response
    }
    logging.info(json.dumps(log_entry))

class Metrics:
    def __init__(self):
        self.counters = defaultdict(int)
        self.timers = defaultdict(list)
        self._lock = asyncio.Lock()

    async def increment(self, metric: str, value: int = 1):
        async with self._lock:
            self.counters[metric] += value

    async def record_time(self, metric: str, duration: float):
        async with self._lock:
            self.timers[metric].append(duration)