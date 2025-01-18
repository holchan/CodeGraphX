import gradio as gr
import sqlite3
import signal
import sys
import argparse
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager
from config.settings import settings
from database.schema import init_database
from database.connection import DatabasePool
from modules.repository import RepositoryManager
from modules.chat import ChatManager
from modules.search import SearchManager
from ui.app import create_app

class Application:
    def __init__(self):
        self.db_pool: Optional[DatabasePool] = None
        self.app: Optional[gr.Blocks] = None
        self.managers: Dict[str, Any] = {}
        self.shutdown_event = asyncio.Event()
        self._setup_logging()
        
    def _setup_logging(self):
        """Configure application logging"""
        log_dir = Path(settings.LOG_FILE).parent
        log_dir.mkdir(parents=True, exist_ok=True)
        
        logging.getLogger().handlers.clear()
        
        logging.basicConfig(
            level=getattr(logging, settings.LOG_LEVEL),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(str(settings.LOG_FILE)),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
        self.logger.info("Logging initialized")

    @asynccontextmanager
    async def lifespan(self):
        """Application lifespan context manager"""
        try:
            await self.initialize()
            yield
        finally:
            await self.cleanup()

    async def initialize(self):
        """Initialize application components"""
        self.logger.info("Initializing application...")
        try:
            db_path = Path(settings.DATABASE_PATH)
            self.logger.info(f"Using database path: {db_path}")
            
            db_path.parent.mkdir(parents=True, exist_ok=True)
            
            init_database(str(db_path))
            self.logger.info("Database initialized successfully")
            
            self.db_pool = DatabasePool(
                str(db_path),
                max_connections=settings.MAX_DB_CONNECTIONS,
                timeout=settings.DB_TIMEOUT
            )
            self.logger.info("Attempting to validate database connections...")
            await self.db_pool.validate_connections()
            self.logger.info("Database pool created and validated")
            
            self.logger.info("Initializing managers...")
            self.managers = {
                "repository_manager": await RepositoryManager().__aenter__(),
                "chat_manager": await ChatManager().__aenter__(),
                "search_manager": SearchManager()
            }
            self.logger.info("Managers initialized successfully")
            
            self.logger.info("Creating Gradio app...")
            self.app = create_app(**self.managers)
            if not isinstance(self.app, gr.Blocks):
                raise ValueError("Invalid app instance created")
            self.logger.info("Gradio app created successfully")
            
        except Exception as e:
            self.logger.error(f"Initialization error: {str(e)}")
            await self.cleanup()
            raise

    def _signal_handler(self, signum: int, frame: Any) -> None:
        """Handle shutdown signals"""
        self.logger.info(f"Received signal {signum}")
        if not self.shutdown_event.is_set():
            self.logger.info("Initiating graceful shutdown...")
            asyncio.create_task(self.shutdown())

    async def shutdown(self):
        """Initiate graceful shutdown"""
        self.shutdown_event.set()
        await self.cleanup()
        sys.exit(0)

    async def cleanup(self):
        """Enhanced cleanup with guaranteed resource release"""
        cleanup_tasks = []
        try:
            async with asyncio.timeout(10):
                if self.db_pool:
                    await self.db_pool.close_all()
                        
                for name, manager in self.managers.items():
                    if hasattr(manager, '__aexit__'):
                        task = asyncio.create_task(
                            manager.__aexit__(None, None, None),
                            name=f"cleanup_{name}"
                        )
                        cleanup_tasks.append(task)
                    
                if cleanup_tasks:
                    done, pending = await asyncio.wait(
                        cleanup_tasks,
                        timeout=8.0,
                        return_when=asyncio.ALL_COMPLETED
                    )
                        
                    for task in pending:
                        task.cancel()

                    if pending:
                        await asyncio.wait(pending, timeout=2.0)
                        
        except asyncio.TimeoutError:
            self.logger.error("Cleanup operation timed out")
        except Exception as e:
            self.logger.error(f"Error during cleanup: {str(e)}")
        finally:
            # Ensure Gradio app is properly closed
            if self.app:
                self.app.close()
            for task in cleanup_tasks:
                if not task.done():
                    task.cancel()

    async def start(self, host: str, port: int):
        """Start the application"""
        try:
            self.logger.info(f"Starting server on {host}:{port}")
            
            if not self.app:
                raise ValueError("Gradio app not initialized")
                
            self.logger.info("Launching Gradio server...")
            self.app.launch(
                server_name=host,
                server_port=port,
                prevent_thread_lock=True,
                show_error=True,
                quiet=False
            )
            
            self.logger.info(f"Server started successfully on http://{host}:{port}")
            
            await self.shutdown_event.wait()
            
        except Exception as e:
            self.logger.error(f"Error starting server: {str(e)}")
            await self.cleanup()
            raise

async def main():
    """Application entry point"""
    parser = argparse.ArgumentParser(description="CodeGraph Frontend")
    parser.add_argument("--host", default="127.0.0.1", help="Host to run the server on")
    parser.add_argument("--port", type=int, default=7860, help="Port to run the server on")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    args = parser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    
    try:
        logger.info(f"Starting application on {args.host}:{args.port}")
        app = Application()

        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda s, f: asyncio.create_task(app.shutdown()))
        
        async with app.lifespan():
            logger.info("Application initialized, launching server...")
            await app.start(args.host, args.port)
            
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        logger.exception("Detailed traceback:")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())