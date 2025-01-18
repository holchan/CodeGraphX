import logging
import time
from uuid import uuid4
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from database.connection import get_db_connection
from .types import SearchType, SearchHistoryItem
from .exceptions import DatabaseError
from sqlite3 import Connection
from functools import lru_cache
from dataclasses import dataclass
from config.settings import settings
from .metrics import Metrics
from .validation import validate_input
from .logging_utils import log_request_response

class SearchCache:
    def __init__(self, max_size=1000, ttl=300):
        self.cache = {}
        self.max_size = max_size
        self.ttl = ttl
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            if key in self.cache:
                entry = self.cache[key]
                if time.time() - entry['timestamp'] < self.ttl:
                    return entry['data']
                del self.cache[key]
            return None

    async def set(self, key: str, value: Any):
        async with self._lock:
            if len(self.cache) >= self.max_size:
                oldest = min(self.cache.items(), key=lambda x: x[1]['timestamp'])
                del self.cache[oldest[0]]
            self.cache[key] = {
                'data': value,
                'timestamp': time.time()
            }

    async def cleanup(self):
        """Periodic cleanup of expired entries"""
        async with self._lock:
            now = time.time()
            expired = [k for k, v in self.cache.items() 
                      if now - v['timestamp'] > self.ttl]
            for k in expired:
                del self.cache[k]

@dataclass
class SearchCriteria:
    query: Optional[str] = None
    search_type: Optional[SearchType] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    repository_ids: Optional[List[str]] = None
    page: int = 1
    page_size: int = settings.pagination.chat_history_page_size

class SearchManager:
    def __init__(self, db_connection: Optional[Connection] = None):
        self.db_connection = db_connection
        self._cache = {}
        self.metrics = Metrics()
    
    def get_search_types(self) -> List[SearchType]:
        return list(SearchType)

    @lru_cache(maxsize=100)
    async def search(self, criteria: SearchCriteria) -> Dict[str, any]:
        """Enhanced search with multiple criteria and caching"""
        try:
            validate_input({
                "criteria": criteria,
            }, {
                "criteria": SearchCriteria
            })

            await self.metrics.increment("search_attempts")
            start_time = time.time()

            request_data = {
                "query": criteria.query,
                "search_type": criteria.search_type.value if criteria.search_type else None,
                "start_date": criteria.start_date.isoformat() if criteria.start_date else None,
                "end_date": criteria.end_date.isoformat() if criteria.end_date else None,
                "repository_ids": criteria.repository_ids,
                "page": criteria.page,
                "page_size": criteria.page_size
            }

            await log_request_response(request_data, None)

            try:
                with get_db_connection() as conn:
                    try:
                        query_parts = ["SELECT ch.*, GROUP_CONCAT(r.url) as repository_urls FROM chat_history ch"]
                        params = []
                        
                        # ... [rest of the query building code] ...
                        
                        response_data = {
                            "results": results,
                            "total": total_count,
                            "page": criteria.page,
                            "page_size": criteria.page_size,
                            "total_pages": (total_count + criteria.page_size - 1) // criteria.page_size
                        }

                        await log_request_response(request_data, response_data)

                        await self.metrics.increment("search_success")
                        await self.metrics.record_time("search_duration", time.time() - start_time)

                        return response_data

                    except sqlite3.OperationalError as e:
                        await self.metrics.increment("search_db_operational_errors")
                        logging.error(f"Database operational error: {str(e)}")
                        raise DatabaseError(f"Database operational error: {str(e)}")
                    except sqlite3.IntegrityError as e:
                        await self.metrics.increment("search_db_integrity_errors")
                        logging.error(f"Database integrity error: {str(e)}")
                        raise DatabaseError(f"Database integrity error: {str(e)}")

            except DatabaseError:
                raise
            except Exception as e:
                await self.metrics.increment("search_db_errors")
                logging.error(f"Unexpected database error: {str(e)}")
                raise DatabaseError(f"Unexpected database error: {str(e)}")

        except ValidationError as e:
            await self.metrics.increment("search_validation_errors")
            logging.error(f"Validation error in search: {str(e)}")
            raise
        except DatabaseError:
            raise
        except Exception as e:
            await self.metrics.increment("search_errors")
            logging.error(f"Unexpected error in search: {str(e)}")
            raise BaseError(f"Unexpected error: {str(e)}")

    async def save_search_history(self, query: str, search_type: SearchType, result: Dict) -> None:
        """Save search history with cache invalidation"""
        try:
            validate_input({
                "query": query,
                "search_type": search_type,
                "result": result
            }, {
                "query": str,
                "search_type": SearchType,
                "result": dict
            })

            await self.metrics.increment("search_history_save_attempts")
            start_time = time.time()

            request_data = {
                "query": query,
                "search_type": search_type.value,
                "result": result
            }

            await log_request_response(request_data, None)

            try:
                with get_db_connection() as conn:
                    search_id = str(uuid4())
                    conn.execute("""
                        INSERT INTO chat_history (id, text, user, created_at, search_type)
                        VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?)
                    """, (search_id, query, "user", search_type.value))
                    conn.commit()

                    self.search.cache_clear()

                    response_data = {"status": "success", "search_id": search_id}

                    await log_request_response(request_data, response_data)

                    await self.metrics.increment("search_history_save_success")
                    await self.metrics.record_time("search_history_save_duration", time.time() - start_time)

                    return response_data

            except Exception as e:
                await self.metrics.increment("search_history_save_db_errors")
                logging.error(f"Database error saving search history: {str(e)}")
                raise DatabaseError(f"Error saving search history: {str(e)}")

        except Exception as e:
            await self.metrics.increment("search_history_save_errors")
            logging.error(f"Error in save_search_history: {str(e)}")
            raise

    def clear_cache(self):
        """Clear the search cache"""
        self.search.cache_clear()