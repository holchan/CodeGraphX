import sqlite3
import time
import logging
import asyncio
from contextlib import asynccontextmanager
from typing import Dict, Set
from modules.exceptions import DatabaseError
from config.settings import settings
from modules.metrics import Metrics
from modules.validation import validate_input

class DatabasePool:
    def __init__(self, db_path: str = str(settings.DATABASE_PATH), max_connections: int = 5, timeout: int = 30):
        self.logger = logging.getLogger(__name__)
        
        validate_input({
            "db_path": db_path,
            "max_connections": max_connections,
            "timeout": timeout
        }, {
            "db_path": str,
            "max_connections": int,
            "timeout": int
        })
        
        self.db_path = db_path
        self.max_connections = max_connections
        self.timeout = timeout
        self._lock = asyncio.Lock()
        self._connection_queue = asyncio.Queue(maxsize=max_connections)
        self._active_connections: Set[sqlite3.Connection] = set()
        self.metrics = Metrics()
        
        # Initialize metrics
        self._metrics = {
            "total_connections": 0,
            "active_connections": 0,
            "connection_errors": 0,
            "timeouts": 0
        }

    def _create_connection(self) -> sqlite3.Connection:
        """Create a new database connection"""
        try:
            conn = sqlite3.connect(
                self.db_path,
                timeout=self.timeout,
                check_same_thread=False
            )
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.Error as e:
            self.logger.error(f"Failed to create connection: {str(e)}")
            raise DatabaseError(f"Failed to create connection: {str(e)}")

    def _validate_connection_sync(self, conn: sqlite3.Connection) -> bool:
        """Synchronously validate a connection"""
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
            return True
        except sqlite3.Error:
            return False

    async def get_connection(self) -> sqlite3.Connection:
        """Get a database connection from the pool"""
        async with self._lock:
            try:
                # Try to get connection from queue
                try:
                    conn = await asyncio.wait_for(
                        self._connection_queue.get(),
                        timeout=self.timeout
                    )
                    if self._validate_connection_sync(conn):
                        await self.metrics.increment("connection_success")
                        return conn
                    else:
                        await self._close_connection(conn)
                except asyncio.TimeoutError:
                    self._metrics["timeouts"] += 1

                # Create new connection if under limit
                if len(self._active_connections) < self.max_connections:
                    conn = await asyncio.to_thread(self._create_connection)
                    self._active_connections.add(conn)
                    self._metrics["total_connections"] += 1
                    await self.metrics.increment("connection_success")
                    return conn
                
                raise DatabaseError("Maximum connections reached")

            except Exception as e:
                await self.metrics.increment("connection_errors")
                self.logger.error(f"Error getting connection: {str(e)}")
                raise DatabaseError(f"Failed to get connection: {str(e)}")

    async def return_connection(self, conn: sqlite3.Connection) -> None:
        """Return a connection to the pool"""
        async with self._lock:
            if conn in self._active_connections:
                try:
                    await self._connection_queue.put(conn)
                    await self.metrics.increment("connection_return_success")
                except asyncio.QueueFull:
                    await self._close_connection(conn)
                    await self.metrics.increment("connection_return_errors")

    async def _close_connection(self, conn: sqlite3.Connection):
        """Close a connection"""
        try:
            conn.close()
        except Exception as e:
            self.logger.error(f"Error closing connection: {e}")
        finally:
            self._active_connections.discard(conn)

    async def close_all(self) -> None:
        """Close all connections in the pool"""
        async with self._lock:
            while not self._connection_queue.empty():
                try:
                    conn = await self._connection_queue.get_nowait()
                    conn.close()
                except asyncio.QueueEmpty:
                    break
            
            for conn in list(self._active_connections):
                try:
                    conn.close()
                except Exception:
                    pass
            self._active_connections.clear()

    def get_metrics(self) -> Dict[str, int]:
        """Get pool metrics"""
        return {
            **self._metrics,
            "current_active": len(self._active_connections),
            "queue_size": self._connection_queue.qsize()
        }

    async def validate_connections(self) -> None:
        """Validate all connections in the pool"""
        async with self._lock:
            invalid_connections = []
            for conn in self._active_connections:
                if not self._validate_connection_sync(conn):
                    invalid_connections.append(conn)
            
            for conn in invalid_connections:
                await self._close_connection(conn)
                self._metrics["connection_errors"] += 1

            while len(self._active_connections) < self.max_connections:
                try:
                    conn = self._create_connection()
                    if self._validate_connection_sync(conn):
                        self._active_connections.add(conn)
                        self._metrics["total_connections"] += 1
                except Exception as e:
                    self.logger.error(f"Error creating new connection: {str(e)}")
                    break

# Create global pool instance
pool = DatabasePool(str(settings.DATABASE_PATH))

@asynccontextmanager
async def get_db_connection(max_retries: int = 3, retry_delay: float = 0.5):
    """Async context manager for database connections"""
    conn = None
    try:
        for attempt in range(max_retries):
            try:
                conn = await pool.get_connection()
                yield conn
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    raise DatabaseError(f"Failed to get connection after {max_retries} attempts: {str(e)}")
                await asyncio.sleep(retry_delay)
    finally:
        if conn:
            await pool.return_connection(conn)