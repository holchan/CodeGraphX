import gradio as gr
import logging
from typing import Dict
from pathlib import Path
from config.settings import CHAT_HISTORY_WIDTH, MAIN_PANEL_WIDTH
from modules.repository import RepositoryManager
from modules.chat import ChatManager
from modules.search import SearchManager
from .components import (
    create_repository_interface,
    create_chat_interface,
    create_history_interface
)

def verify_static_files():
    logger = logging.getLogger(__name__)
    css_path = Path(__file__).parent / "static" / "styles.css"
    logger.info(f"Verifying static files... CSS path: {css_path}")
    
    if not css_path.exists():
        logger.error(f"CSS file not found at {css_path}")
        css_path.parent.mkdir(parents=True, exist_ok=True)
        css_path.write_text("/* Default styles */")
        logger.info("Created default CSS file")
    return css_path

def create_app(
    repository_manager: RepositoryManager,
    chat_manager: ChatManager,
    search_manager: SearchManager
) -> gr.Blocks:
    """Create main Gradio application"""
    logger = logging.getLogger(__name__)
    logger.info("Starting to create Gradio application...")
    
    try:
        css_path = Path(__file__).parent / "static" / "styles.css"
        logger.info(f"Looking for CSS file at: {css_path}")
        
        if not css_path.exists():
            raise FileNotFoundError(f"CSS file not found: {css_path}")
        
        logger.info("Creating Gradio Blocks instance...")    
        app = gr.Blocks(css=css_path.read_text())
        
        logger.info("Setting up application layout...")
        with app:
            with gr.Row():
                # History Panel (20% width)
                with gr.Column(scale=20):
                    logger.info("Creating history panel...")
                    history_components = create_history_interface(chat_manager)
                
                # Main Panel (80% width)
                with gr.Column(scale=80):
                    # Repository Management Section
                    logger.info("Setting up repository management...")
                    with gr.Group(elem_classes=["section-container"]):
                        repo_components = create_repository_interface(repository_manager)
                    
                    # Chat Interface Section
                    logger.info("Setting up chat interface...")
                    with gr.Group(elem_classes=["section-container"]):
                        chat_components = create_chat_interface(
                            chat_manager=chat_manager,
                            repository_manager=repository_manager
                        )
        
        logger.info("Gradio application created successfully")
        return app
        
    except Exception as e:
        logger.error(f"Error creating application: {str(e)}")
        logger.exception("Detailed traceback:")
        raise