import httpx
import logging
import sqlite3
from uuid import UUID, uuid4
from typing import Dict, List, Optional, TypedDict, Literal
from datetime import datetime
from config.settings import settings
from database.connection import get_db_connection
from .base import AsyncHTTPClient
from .types import SearchType, SearchHistoryItem, APIResponse
from .exceptions import APIError, DatabaseError, ValidationError
from .metrics import Metrics
from .validation import validate_input
from .logging_utils import log_request_response

class ChatManager(AsyncHTTPClient):
    def __init__(self, base_url: str = settings.API_BASE_URL, timeout: float = settings.timeout.connect_timeout):
        super().__init__(base_url, timeout)
        self.metrics = Metrics()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    def validate_message(text: str, max_length: int = 1000) -> bool:
        try:
            if not text or not text.strip():
                raise ValidationError("Message cannot be empty")
                
            if len(text) > max_length:
                raise ValidationError(f"Message exceeds maximum length of {max_length} characters")
                
            dangerous_chars = ['<', '>', '{', '}', '(', ')', ';']
            if any(char in text for char in dangerous_chars):
                raise ValidationError("Message contains invalid characters")
            
            return True
        
        except Exception as e:
            logging.error(f"Message validation error: {str(e)}")
            raise ValidationError(f"Message validation failed: {str(e)}")

    async def send_message(self, query: str, search_type: SearchType, 
                        parent_id: Optional[UUID] = None) -> APIResponse:
        """Send message with threading support"""
        try:
            # Input validation
            validate_input({
                "query": query,
                "search_type": search_type,
                "parent_id": parent_id
            }, {
                "query": str,
                "search_type": SearchType,
                "parent_id": Optional[UUID]
            })
            
            self.validate_message(query)
            
            # Track metrics
            await self.metrics.increment("chat_message_send_attempts")
            start_time = time.time()
            
            request_data = {
                "search_type": search_type.value,
                "query": query,
                "parent_id": str(parent_id) if parent_id else None
            }
            
            # Log request
            await log_request_response(request_data, None)
            
            try:
                response = await self.client.post("/search", json=request_data)
                response_data = response.json()
                
                if response.status_code == 404:
                    return APIResponse(
                        status="error",
                        message="Search endpoint not found",
                        errors=["Endpoint not found"]
                    )
                elif response.status_code == 422:
                    return APIResponse(
                        status="error",
                        message="Invalid search parameters",
                        errors=[response_data.get('detail', 'Validation error')]
                    )
                elif response.status_code == 400:
                    return APIResponse(
                        status="error",
                        message="Bad request",
                        errors=[response_data.get('detail', 'Bad request')]
                    )
                    
                response.raise_for_status()
                
                # Log response
                await log_request_response(request_data, response_data)
                
                # Record success and timing
                await self.metrics.increment("chat_message_send_success")
                await self.metrics.record_time("chat_message_send_duration", time.time() - start_time)
                
                return APIResponse(
                    status="success",
                    message="Message sent successfully",
                    data=response_data
                )
                
            except httpx.HTTPError as e:
                await self.metrics.increment("chat_message_send_api_errors")
                logging.error(f"HTTP error sending message: {str(e)}")
                return APIResponse(
                    status="error",
                    message="Failed to send message",
                    errors=[str(e)]
                )
                
        except ValidationError as e:
            await self.metrics.increment("chat_message_validation_errors")
            logging.error(f"Validation error: {str(e)}")
            return APIResponse(
                status="error",
                message="Validation error",
                errors=[str(e)]
            )
        except Exception as e:
            await self.metrics.increment("chat_message_send_errors")
            logging.error(f"Unexpected error: {str(e)}")
            return APIResponse(
                status="error",
                message="An unexpected error occurred",
                errors=[str(e)]
            )

    async def edit_message(self, message_id: UUID, new_text: str) -> Dict:
        try:
            # Input validation
            validate_input({
                "message_id": message_id,
                "new_text": new_text
            }, {
                "message_id": UUID,
                "new_text": str
            })
            
            # Track metrics
            await self.metrics.increment("chat_message_edit_attempts")
            start_time = time.time()
            
            request_data = {
                "message_id": str(message_id),
                "new_text": new_text
            }
            
            # Log request
            await log_request_response(request_data, None)
            
            try:
                with get_db_connection() as conn:
                    conn.execute("""
                        UPDATE chat_history 
                        SET text = ? 
                        WHERE id = ?
                    """, (new_text, str(message_id)))
                    conn.commit()
                    
                response_data = {"status": "success", "message": "Message updated"}
                
                # Log response
                await log_request_response(request_data, response_data)
                
                # Record success and timing
                await self.metrics.increment("chat_message_edit_success")
                await self.metrics.record_time("chat_message_edit_duration", time.time() - start_time)
                
                return response_data
                
            except sqlite3.Error as e:
                await self.metrics.increment("chat_message_edit_db_errors")
                logging.error(f"Database error editing message: {str(e)}")
                raise DatabaseError(f"Database error: {str(e)}")
                
        except Exception as e:
            await self.metrics.increment("chat_message_edit_errors")
            logging.error(f"Error in edit_message: {str(e)}")
            raise

    async def exclude_message(self, message_id: UUID) -> Dict:
        try:
            # Input validation
            validate_input({
                "message_id": message_id
            }, {
                "message_id": UUID
            })
            
            # Track metrics
            await self.metrics.increment("chat_message_exclude_attempts")
            start_time = time.time()
            
            request_data = {
                "message_id": str(message_id)
            }
            
            # Log request
            await log_request_response(request_data, None)
            
            try:
                with get_db_connection() as conn:
                    conn.execute("""
                        DELETE FROM chat_history 
                        WHERE id = ?
                    """, (str(message_id),))
                    conn.commit()
                    
                response_data = {"status": "success", "message": "Message excluded"}
                
                # Log response
                await log_request_response(request_data, response_data)
                
                # Record success and timing
                await self.metrics.increment("chat_message_exclude_success")
                await self.metrics.record_time("chat_message_exclude_duration", time.time() - start_time)
                
                return response_data
                
            except sqlite3.Error as e:
                await self.metrics.increment("chat_message_exclude_db_errors")
                logging.error(f"Database error excluding message: {str(e)}")
                raise DatabaseError(f"Database error: {str(e)}")
                
        except Exception as e:
            await self.metrics.increment("chat_message_exclude_errors")
            logging.error(f"Error in exclude_message: {str(e)}")
            raise

    async def save_message(self, text: str, user: str, search_type: str, 
                        repository_ids: List[str], parent_id: Optional[UUID] = None) -> Dict[str, str]:
        """Save message with threading support"""
        async with self.metrics.timer("chat_message_save_duration"):
            try:
                # Input validation
                validate_input({
                    "text": text,
                    "user": user,
                    "search_type": search_type,
                    "repository_ids": repository_ids,
                    "parent_id": parent_id
                }, {
                    "text": str,
                    "user": str,
                    "search_type": str,
                    "repository_ids": List[str],
                    "parent_id": Optional[UUID]
                })
                
                self.validate_message(text)
                await self.metrics.increment("chat_message_save_attempts")
                
                request_data = {
                    "text": text,
                    "user": user,
                    "search_type": search_type,
                    "repository_ids": repository_ids,
                    "parent_id": str(parent_id) if parent_id else None
                }
                
                await log_request_response(request_data, None)
                
                async with get_db_connection() as conn:
                    async with conn.transaction():
                        message_id = str(uuid4())
                        
                        # Get thread position atomically
                        thread_position = await conn.fetchval("""
                            SELECT COALESCE(MAX(thread_position), 0) + 1
                            FROM chat_history 
                            WHERE COALESCE(parent_id, id) = COALESCE($1, $2)
                        """, str(parent_id) if parent_id else message_id,
                            str(parent_id) if parent_id else message_id)
                        
                        await conn.execute("""
                            INSERT INTO chat_history (
                                id, text, user, created_at, search_type, 
                                repository_ids, parent_id, thread_position
                            )
                            VALUES ($1, $2, $3, CURRENT_TIMESTAMP, $4, $5, $6, $7)
                        """, message_id, text, user, search_type, 
                            ','.join(repository_ids), parent_id, thread_position)
                        
                        response_data = {"status": "success", "message_id": message_id}
                        await log_request_response(request_data, response_data)
                        await self.metrics.increment("chat_message_save_success")
                        
                        return response_data
                        
            except ValidationError as e:
                await self.metrics.increment("chat_message_validation_errors")
                logging.error(f"Validation error in save_message: {str(e)}")
                raise
            except DatabaseError as e:
                await self.metrics.increment("chat_message_save_db_errors")
                logging.error(f"Database error in save_message: {str(e)}")
                raise
            except Exception as e:
                await self.metrics.increment("chat_message_save_errors")
                logging.error(f"Unexpected error in save_message: {str(e)}")
                raise

    async def get_chat_history_with_context(self, page: int = 1, page_size: Optional[int] = None) -> Dict[str, any]:
        try:
            # Input validation
            validate_input({
                "page": page,
                "page_size": page_size
            }, {
                "page": int,
                "page_size": Optional[int]
            })
            
            # Track metrics
            await self.metrics.increment("chat_history_get_attempts")
            start_time = time.time()
            
            if page_size is None:
                page_size = settings.pagination.chat_history_page_size
                
            offset = (page - 1) * page_size
            
            request_data = {
                "page": page,
                "page_size": page_size,
                "offset": offset
            }
            
            # Log request
            await log_request_response(request_data, None)
            
            try:
                with get_db_connection() as conn:
                    total_count = conn.execute(
                        "SELECT COUNT(*) FROM chat_history"
                    ).fetchone()[0]
                    
                    cursor = conn.execute("""
                        SELECT 
                            ch.*, 
                            GROUP_CONCAT(r.url) as repository_urls,
                            (SELECT COUNT(*) FROM chat_history WHERE parent_id = ch.id) as reply_count
                        FROM chat_history ch
                        LEFT JOIN repositories r ON r.dataset_id IN (
                            SELECT value 
                            FROM json_each('["' || REPLACE(ch.repository_ids, ',', '","') || '"]')
                        )
                        GROUP BY ch.id
                        ORDER BY 
                            COALESCE(ch.parent_id, ch.id),
                            ch.thread_position,
                            ch.created_at DESC
                        LIMIT ? OFFSET ?
                    """, (page_size, offset))
                    
                    messages = [dict(row) for row in cursor.fetchall()]
                    
                    response_data = {
                        "messages": messages,
                        "total": total_count,
                        "page": page,
                        "page_size": page_size,
                        "total_pages": (total_count + page_size - 1) // page_size
                    }
                    
                    # Log response
                    await log_request_response(request_data, response_data)
                    
                    # Record success and timing
                    await self.metrics.increment("chat_history_get_success")
                    await self.metrics.record_time("chat_history_get_duration", time.time() - start_time)
                    
                    return response_data
                    
            except sqlite3.Error as e:
                await self.metrics.increment("chat_history_get_db_errors")
                logging.error(f"Database error getting chat history: {str(e)}")
                raise DatabaseError(f"Database error: {str(e)}")
                
        except Exception as e:
            await self.metrics.increment("chat_history_get_errors")
            logging.error(f"Error in get_chat_history: {str(e)}")
            raise

    async def update_message_repositories(self, message_id: UUID, repository_ids: List[str]) -> Dict:
        try:
            # Input validation
            validate_input({
                "message_id": message_id,
                "repository_ids": repository_ids
            }, {
                "message_id": UUID,
                "repository_ids": List[str]
            })
            
            # Track metrics
            await self.metrics.increment("message_repositories_update_attempts")
            start_time = time.time()
            
            request_data = {
                "message_id": str(message_id),
                "repository_ids": repository_ids
            }
            
            # Log request
            await log_request_response(request_data, None)
            
            try:
                with get_db_connection() as conn:
                    conn.execute("""
                        UPDATE chat_history 
                        SET repository_ids = ?
                        WHERE id = ?
                    """, (','.join(repository_ids), str(message_id)))
                    conn.commit()
                    
                response_data = {"status": "success", "message": "Repository context updated"}
                
                # Log response
                await log_request_response(request_data, response_data)
                
                # Record success and timing
                await self.metrics.increment("message_repositories_update_success")
                await self.metrics.record_time("message_repositories_update_duration", time.time() - start_time)
                
                return response_data
                
            except sqlite3.Error as e:
                await self.metrics.increment("message_repositories_update_db_errors")
                logging.error(f"Database error updating repositories: {str(e)}")
                raise DatabaseError(f"Database error: {str(e)}")
                
        except Exception as e:
            await self.metrics.increment("message_repositories_update_errors")
            logging.error(f"Error in update_message_repositories: {str(e)}")
            raise