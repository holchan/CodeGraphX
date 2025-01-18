import sqlite3
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

CREATE_TABLES_SQL = """
-- Enable foreign key support
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS repositories (
    dataset_id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    branch TEXT,
    status TEXT NOT NULL CHECK (status IN ('active', 'inactive', 'syncing', 'error')),
    last_sync TIMESTAMP,
    is_active BOOLEAN DEFAULT true,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_history (
    id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    user TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    search_type TEXT NOT NULL,
    repository_ids TEXT, -- Comma-separated list of dataset_ids
    parent_id TEXT,
    FOREIGN KEY (parent_id) REFERENCES chat_history(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    value TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_chat_history_repository_ids ON chat_history(repository_ids);
CREATE INDEX IF NOT EXISTS idx_chat_history_created_at ON chat_history(created_at);
CREATE INDEX IF NOT EXISTS idx_chat_history_user ON chat_history(user);
CREATE INDEX IF NOT EXISTS idx_chat_history_search_type ON chat_history(search_type);
CREATE INDEX IF NOT EXISTS idx_repositories_status ON repositories(status);
CREATE INDEX IF NOT EXISTS idx_repositories_is_active ON repositories(is_active);
CREATE INDEX IF NOT EXISTS idx_repositories_url ON repositories(url);
CREATE INDEX IF NOT EXISTS idx_repositories_updated_at ON repositories(updated_at);
CREATE INDEX IF NOT EXISTS idx_chat_history_updated_at ON chat_history(updated_at);

-- Triggers for updated_at timestamps
CREATE TRIGGER IF NOT EXISTS repositories_updated_at 
    AFTER UPDATE ON repositories
BEGIN
    UPDATE repositories SET updated_at = CURRENT_TIMESTAMP WHERE dataset_id = NEW.dataset_id;
END;

CREATE TRIGGER IF NOT EXISTS chat_history_updated_at 
    AFTER UPDATE ON chat_history
BEGIN
    UPDATE chat_history SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS user_preferences_updated_at 
    AFTER UPDATE ON user_preferences
BEGIN
    UPDATE user_preferences SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;
"""

def init_database(db_path: str):
    """Initialize database with required tables"""
    try:
        conn = sqlite3.connect(db_path)
        
        # Enable foreign keys
        conn.execute("PRAGMA foreign_keys = ON")
        
        # Create tables
        conn.executescript(CREATE_TABLES_SQL)
        
        # Verify foreign key support
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys")
        if not cursor.fetchone()[0]:
            raise Exception("Foreign key support could not be enabled")
            
        conn.commit()
        logging.info("Database initialized successfully")
    except Exception as e:
        logging.error(f"Failed to initialize database: {str(e)}")
        raise
    finally:
        if conn:
            conn.close()