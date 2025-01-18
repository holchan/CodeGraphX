import gradio as gr
from gradio.components import Component
from typing import Dict, List, Optional
from datetime import datetime
from .shared import LoadingContext
from .base_ui import with_error_boundary, with_loading_state

def create_history_interface(chat_manager) -> Dict[str, Component]:
    with gr.Column(scale=20) as history_container:
        gr.Markdown("### Chat History")
        
        with gr.Row():
            search_input = gr.Textbox(
                label="Search Chats",
                placeholder="Search in chat history...",
                show_label=False
            )
            date_filter = gr.Dropdown(
                choices=["All Time", "Today", "Last Week", "Last Month"],
                value="All Time",
                label="Time Filter"
            )

        history_list = gr.HTML(
            value="<div class='chat-history-list'></div>",
            elem_classes=["chat-history-container"]
        )

        loading_indicator = gr.HTML(
            value='<div class="loading-spinner" style="display:none"></div>',
            visible=False
        )

        # Hidden refresh button for auto-refresh functionality
        refresh_btn = gr.Button("Refresh", visible=False)

    @with_error_boundary
    @with_loading_state([history_list])
    async def load_chat_history(search_query: str = "", time_filter: str = "All Time"):
        """Load and display chat history"""
        try:
            async with LoadingContext([history_list]):
                loading_indicator.visible = True
                
                history = await chat_manager.get_chat_history_with_context()
                
                history_html = "<div class='chat-history-list'>"
                for chat in history["messages"]:
                    timestamp = datetime.fromisoformat(chat["created_at"]).strftime("%Y-%m-%d %H:%M")
                    history_html += f"""
                        <div class='chat-history-item' data-id='{chat["id"]}'>
                            <div class='chat-history-header'>
                                <span class='chat-time'>{timestamp}</span>
                                <span class='chat-type'>{chat["search_type"]}</span>
                            </div>
                            <div class='chat-preview'>{chat["text"][:100]}...</div>
                        </div>
                    """
                history_html += "</div>"
                
                history_list.value = history_html
                return history_html
        except Exception as e:
            gr.Error(f"Error loading chat history: {str(e)}")
            return "<div class='error-message'>Failed to load chat history</div>"
        finally:
            loading_indicator.visible = False

    # Set up event handlers
    search_input.change(
        fn=load_chat_history,
        inputs=[search_input, date_filter],
        outputs=[history_list]
    )
    
    date_filter.change(
        fn=load_chat_history,
        inputs=[search_input, date_filter],
        outputs=[history_list]
    )

    # Initial load and auto-refresh using JavaScript
    gr.HTML("""
        <script>
            document.addEventListener('DOMContentLoaded', function() {
                // Initial load
                setTimeout(function() {
                    document.querySelector('button[id$="-refresh"]').click();
                }, 100);
                
                // Auto-refresh every 30 seconds
                setInterval(function() {
                    document.querySelector('button[id$="-refresh"]').click();
                }, 30000);
            });
        </script>
    """)

    # Refresh button handler
    refresh_btn.click(
        fn=load_chat_history,
        inputs=[search_input, date_filter],
        outputs=[history_list]
    )

    return {
        "container": history_container,
        "search_input": search_input,
        "date_filter": date_filter,
        "history_list": history_list,
        "loading_indicator": loading_indicator,
        "refresh_btn": refresh_btn
    }