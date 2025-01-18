import gradio as gr
from gradio.components import Component
from functools import wraps
from typing import Callable, Any, List
import time
from datetime import datetime, timedelta

class RateLimiter:
    def __init__(self, max_calls: int, time_window: float):
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = {}
        self._cleanup_interval = 60.0
        self._last_cleanup = time.time()

    def can_proceed(self, user_id: str) -> bool:
        self._cleanup_old_entries()
        now = time.time()
        user_calls = self.calls.get(user_id, [])
        user_calls = [call for call in user_calls if call > now - self.time_window]
        if len(user_calls) >= self.max_calls:
            return False
        user_calls.append(now)
        self.calls[user_id] = user_calls
        return True

    def _cleanup_old_entries(self):
        """Clean up old entries periodically"""
        if time.time() - self._last_cleanup >= self._cleanup_interval:
            now = time.time()
            self.calls = {
                user_id: [call for call in calls if call > now - self.time_window]
                for user_id, calls in self.calls.items()
            }
            self._last_cleanup = time.time()

def with_rate_limit(max_calls: int = 5, time_window: float = 60.0):
    limiter = RateLimiter(max_calls, time_window)
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, user_id: str = "default_user", **kwargs):
            if not limiter.can_proceed(user_id):
                raise gr.Error("Rate limit exceeded. Please wait before sending more messages.")
            return await func(*args, **kwargs)
        return wrapper
    return decorator

class LoadingIndicator:
    def __init__(self):
        self.loading_html = gr.HTML(
            value='<div class="loading-spinner"></div>',
            visible=False,
            elem_classes=["custom-loading-indicator"]
        )
        self.status_text = gr.Markdown(
            value="",
            visible=False
        )
        self.is_rendered = False

    def show(self, message: str = "Processing..."):
        """Show the loading indicator"""
        self.loading_html.visible = True
        self.status_text.value = message
        self.status_text.visible = True

    def hide(self):
        """Hide the loading indicator"""
        self.loading_html.visible = False
        self.status_text.visible = False

    def create(self, operation_name: str) -> gr.HTML:
        """Create a new loading indicator HTML element"""
        return gr.HTML(
            value=f'''
            <div class="loading-indicator">
                <div class="spinner"></div>
                <div class="operation-text">{operation_name}</div>
            </div>
            ''',
            visible=False,
            elem_classes=["custom-loading-indicator"]
        )

def validate_repository_url(url: str) -> bool:
    """Shared repository URL validation"""
    if not url or not url.strip():
        raise gr.Error("Repository URL cannot be empty")
    if not url.startswith(('http://', 'https://', 'git://')):
        raise gr.Error("Invalid repository URL scheme")
    return True

def validate_message(text: str, max_length: int = 1000) -> bool:
    """Shared message validation"""
    if not text or not text.strip():
        raise gr.Error("Message cannot be empty")
    if len(text) > max_length:
        raise gr.Error(f"Message exceeds maximum length of {max_length} characters")
    return True

class LoadingContext:
    """Consistent loading state handling"""
    def __init__(self, components: List[Any]):
        self.components = components

    async def __aenter__(self):
        for component in self.components:
            component.interactive = False
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        for component in self.components:
            component.interactive = True