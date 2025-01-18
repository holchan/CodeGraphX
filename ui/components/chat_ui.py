import gradio as gr
from gradio.components import Component, HTML, Chatbot, Checkbox, Dropdown, Textbox, Button
from typing import Dict, List, Optional
from uuid import UUID
import logging
from datetime import datetime, timedelta
from .shared import validate_message, with_rate_limit, LoadingContext
from modules.chat import ChatManager
from modules.repository import RepositoryManager

class ChatInterface:
    def __init__(self, chat_manager: ChatManager, repository_manager: RepositoryManager):
        self.chat_manager = chat_manager
        self.repository_manager = repository_manager
        self.last_message_time = datetime.now()
        self.message_count = 0
        self.rate_limit_window = timedelta(minutes=1)
        self.max_messages_per_window = 5

    def create_interface(self) -> Dict[str, Component]:
        with gr.Blocks() as demo:
            typing_indicator = gr.HTML(
                value='<div class="typing-indicator" style="display:none">'
                    '<span></span><span></span><span></span>'
                    '</div>',
                visible=False
            )

            with gr.Column() as main_container:
                # Chat History Display
                chatbot = gr.Chatbot(
                    show_label=False,
                    height=500,
                    container=True,
                    bubble_full_width=False,
                    avatar_images=("user.png", "bot.png")
                )

                # Thread View Controls
                with gr.Row():
                    thread_view = gr.Checkbox(
                        label="Thread View",
                        value=False,
                        interactive=True
                    )
                    search_type = gr.Dropdown(
                        choices=["SUMMARIES", "INSIGHTS", "CHUNKS", "COMPLETION"],
                        label="Search Type",
                        value="COMPLETION",
                        interactive=True
                    )
                    active_repos = gr.Dropdown(
                        multiselect=True,
                        label="Active Repositories",
                        interactive=True
                    )

                # Message Input Area
                with gr.Row():
                    msg_input = gr.Textbox(
                        label="Message",
                        placeholder="Type your message here...",
                        lines=2,
                        max_lines=5,
                        show_copy_button=True
                    )
                    with gr.Column(scale=1):
                        send_btn = gr.Button("Send", variant="primary")
                        redo_btn = gr.Button("Redo Last")

                # Message Controls
                with gr.Row(visible=False) as message_controls:
                    edit_btn = gr.Button("Edit")
                    exclude_btn = gr.Button("Exclude")
                    reply_btn = gr.Button("Reply")

                # Status Message
                status_msg = gr.Textbox(
                    label="Status",
                    interactive=False,
                    visible=False
                )

                # Error Display
                error_box = gr.HTML(visible=False)

            async def check_rate_limit() -> bool:
                """Check if message sending is within rate limits"""
                current_time = datetime.now()
                if current_time - self.last_message_time > self.rate_limit_window:
                    self.message_count = 0
                    self.last_message_time = current_time
                
                if self.message_count >= self.max_messages_per_window:
                    remaining_time = (self.last_message_time + self.rate_limit_window - current_time).seconds
                    raise gr.Error(f"Rate limit exceeded. Please wait {remaining_time} seconds.")
                
                self.message_count += 1
                return True

            @with_rate_limit(max_calls=5, time_window=60)
            async def send_message(
                message: str,
                search_type: str,
                active_repositories: List[str]
            ) -> tuple[str, str]:
                """Handle message sending with validation and rate limiting"""
                try:
                    validate_message(message)
                    await check_rate_limit()

                    async with LoadingContext([send_btn, msg_input]):
                        typing_indicator.visible = True
                        try:
                            # Send message to API
                            response = await self.chat_manager.send_message(
                                query=message,
                                search_type=search_type,
                                repository_ids=active_repositories
                            )
                            
                            # Update chat display
                            chatbot.value = await self.chat_manager.get_chat_history_with_context(
                                thread_view=thread_view.value
                            )
                            return "", "Message sent successfully"
                        finally:
                            typing_indicator.visible = False
                except Exception as e:
                    error_box.value = f"<div class='error-message'>{str(e)}</div>"
                    error_box.visible = True
                    return message, f"Error: {str(e)}"

            async def redo_last_message() -> str:
                """Redo the last message with error handling"""
                try:
                    async with LoadingContext([redo_btn]):
                        history = await self.chat_manager.get_chat_history_with_context(limit=1)
                        if not history:
                            return "No message to redo"
                        
                        last_message = history[0]
                        await self.chat_manager.send_message(
                            query=last_message["text"],
                            search_type=last_message["search_type"]
                        )
                        
                        chatbot.value = await self.chat_manager.get_chat_history_with_context(
                            thread_view=thread_view.value
                        )
                        return "Message redone successfully"
                except Exception as e:
                    logging.error(f"Error redoing message: {str(e)}")
                    return f"Error: {str(e)}"

            async def edit_message(message_id: str, new_text: str) -> str:
                """Edit an existing message"""
                try:
                    async with LoadingContext([edit_btn]):
                        validate_message(new_text)
                        await self.chat_manager.edit_message(UUID(message_id), new_text)
                        chatbot.value = await self.chat_manager.get_chat_history_with_context(
                            thread_view=thread_view.value
                        )
                        return "Message updated successfully"
                except Exception as e:
                    logging.error(f"Error editing message: {str(e)}")
                    return f"Error: {str(e)}"

            async def exclude_message(message_id: str) -> str:
                """Exclude a message from the chat history"""
                try:
                    async with LoadingContext([exclude_btn]):
                        await self.chat_manager.exclude_message(UUID(message_id))
                        chatbot.value = await self.chat_manager.get_chat_history_with_context(
                            thread_view=thread_view.value
                        )
                        return "Message excluded successfully"
                except Exception as e:
                    logging.error(f"Error excluding message: {str(e)}")
                    return f"Error: {str(e)}"

            async def update_active_repositories():
                """Update the list of active repositories"""
                try:
                    repos = await self.repository_manager.get_repositories_status()
                    active_repos.choices = [
                        (str(r["dataset_id"]), r["url"]) 
                        for r in repos 
                        if r["status"] == "active"
                    ]
                except Exception as e:
                    logging.error(f"Error updating repositories: {str(e)}")
                    error_box.value = f"<div class='error-message'>Error updating repositories: {str(e)}</div>"
                    error_box.visible = True

            async def toggle_thread_view(show_threads: bool):
                """Toggle between threaded and flat message view"""
                try:
                    chatbot.thread_view = show_threads
                    return await self.chat_manager.get_chat_history_with_context(
                        thread_view=show_threads
                    )
                except Exception as e:
                    logging.error(f"Error toggling thread view: {str(e)}")
                    return chatbot.value

            # Connect event handlers
            send_btn.click(
                fn=send_message,
                inputs=[msg_input, search_type, active_repos],
                outputs=[msg_input, status_msg]
            )
            
            redo_btn.click(
                fn=redo_last_message,
                outputs=[status_msg]
            )
            
            edit_btn.click(
                fn=edit_message,
                inputs=[gr.State("message_id"), gr.State("new_text")],
                outputs=[status_msg]
            )
            
            exclude_btn.click(
                fn=exclude_message,
                inputs=[gr.State("message_id")],
                outputs=[status_msg]
            )

            thread_view.change(
                fn=toggle_thread_view,
                inputs=[thread_view],
                outputs=[chatbot]
            )

            demo.load(
                fn=update_active_repositories,
                outputs=[active_repos, error_box],
                every=30  # This handles both initial load and periodic updates
            )

            return {
                "demo": demo,
                "main_container": main_container,
                "chatbot": chatbot,
                "search_type": search_type,
                "active_repos": active_repos,
                "msg_input": msg_input,
                "send_btn": send_btn,
                "redo_btn": redo_btn,
                "edit_btn": edit_btn,
                "exclude_btn": exclude_btn,
                "reply_btn": reply_btn,
                "status_msg": status_msg,
                "message_controls": message_controls,
                "typing_indicator": typing_indicator,
                "thread_view": thread_view,
                "error_box": error_box
            }

class LoadingState:
    def __init__(self, components: List[Component]):
        self.components = components
        self.loading_indicator = HTML(
            visible=False,
            value='<div class="loading-spinner"></div>'
        )

    async def __aenter__(self):
        for component in self.components:
            component.interactive = False
        self.loading_indicator.visible = True
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.loading_indicator.visible = False
        for component in self.components:
            component.interactive = True

def create_chat_interface(
    chat_manager: ChatManager,
    repository_manager: RepositoryManager
) -> Dict[str, Component]:
    interface = ChatInterface(chat_manager, repository_manager)
    return interface.create_interface()