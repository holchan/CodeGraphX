import gradio as gr
from gradio.components import Component
from typing import Dict, List
from .shared import validate_repository_url, LoadingContext, LoadingIndicator
from ..components.base_ui import with_error_boundary, with_loading_state

def create_repository_interface(repository_manager) -> Dict[str, Component]:
    with gr.Blocks() as demo:
        loading = LoadingIndicator()
        
        with gr.Column() as main_container:
            gr.Markdown("# Repository Management")
            gr.Markdown("Add and manage Git repositories for processing")
            
            error_display = gr.HTML(
                value="",
                visible=False,
                elem_classes=["error-message"]
            )

            # Repository Add Section
            with gr.Row(elem_classes=["repository-add"]):
                with gr.Column(scale=3):
                    url_input = gr.Textbox(
                        label="Repository URL",
                        placeholder="https://github.com/user/repo",
                        elem_classes=["repository-input"],
                        info="Enter the HTTPS URL of the Git repository"
                    )
                with gr.Column(scale=2):
                    branch_input = gr.Textbox(
                        label="Branch",
                        placeholder="main",
                        elem_classes=["repository-input"],
                        info="Optional: Specify a branch name"
                    )
                with gr.Column(scale=1):
                    add_btn = gr.Button(
                        "Add Repository",
                        variant="primary",
                        elem_classes=["action-button"]
                    )

            loading_status = loading.loading_html
            status_text = loading.status_text

            # Action Buttons
            with gr.Row(elem_classes=["repository-actions"]):
                refresh_btn = gr.Button(
                    "🔄 Refresh",
                    variant="secondary",
                    scale=1
                )
                sync_btn = gr.Button(
                    "🔄 Sync Selected",
                    variant="secondary",
                    scale=1
                )
                toggle_btn = gr.Button(
                    "⚡ Toggle Active",
                    variant="secondary",
                    scale=1
                )
                delete_btn = gr.Button(
                    "🗑️ Delete Selected",
                    variant="secondary",
                    scale=1
                )

            # Status Table
            with gr.Row(elem_classes=["repository-status"]):
                status_table = gr.DataFrame(
                    headers=["Dataset ID", "URL", "Status", "Last Sync", "Active", "Error"],
                    label="Repositories",
                    interactive=True,
                    wrap=True,
                    col_count=(6, "fixed"),
                    elem_classes=["status-table"]
                )

            with gr.Row():
                sync_status = gr.HTML(
                    value='<div class="sync-status"></div>',
                    visible=True,
                    elem_classes=["sync-status-container"]
                )

            status_message = gr.Textbox(
                label="Status",
                interactive=False,
                elem_classes=["status-message"]
            )

    async def update_sync_status(repos):
        """Update sync status display with visual indicators"""
        status_html = '<div class="sync-status">'
        for repo in repos:
            status_class = f"status-{repo['status'].lower()}"
            status_html += f'''
                <div class="status-row {status_class}">
                    <span class="status-indicator"></span>
                    <span class="status-text">{repo['url']}</span>
                    <span class="status-text">{repo['status']}</span>
                    {f'<span class="status-text">Last sync: {repo["last_sync"].strftime("%Y-%m-%d %H:%M:%S")}</span>' 
                    if repo["last_sync"] else ''}
                    {f'<span class="error-message">{repo["error_message"]}</span>' 
                    if repo["error_message"] else ''}
                </div>
            '''
        status_html += '</div>'
        sync_status.value = status_html

    @with_error_boundary
    @with_loading_state([add_btn, url_input, branch_input])
    async def handle_add_repository(url: str, branch: str):
        try:
            validate_repository_url(url)
            loading.show("Adding repository...")
            async with LoadingContext([add_btn, url_input, branch_input]):
                result = await repository_manager.add_repository(url, branch)
                repos = await refresh_status()
                await update_sync_status(repos)
                error_display.visible = False
                loading.hide()
                return "", "", f"Successfully added repository: {result.data['dataset_id']}"
        except Exception as e:
            loading.hide()
            error_display.value = f"<div class='error-message'>{str(e)}</div>"
            error_display.visible = True
            return url, branch, f"Error: {str(e)}"

    async def refresh_status():
        try:
            repos = await repository_manager.get_repositories_status()
            await update_sync_status(repos)
            return [[
                r["dataset_id"],
                r["url"],
                r["status"],
                r["last_sync"].strftime("%Y-%m-%d %H:%M:%S") if r["last_sync"] else "",
                "Yes" if r["is_active"] else "No",
                r["error_message"] or ""
            ] for r in repos]
        except Exception as e:
            error_display.value = f"<div class='error-message'>Error refreshing status: {str(e)}</div>"
            error_display.visible = True
            raise

    async def handle_sync(table_data) -> str:
        """Handle syncing selected repositories"""
        try:
            # Extract selected rows from table_data
            selected_ids = [row[0] for row in table_data if row and len(row) > 0]
            
            if not selected_ids:
                return "No repositories selected"

            async with LoadingContext([sync_btn]):
                for dataset_id in selected_ids:
                    await repository_manager.sync_repository(dataset_id)
                await refresh_status()
                return "Sync initiated for selected repositories"
        except Exception as e:
            error_display.value = f"<div class='error-message'>{str(e)}</div>"
            error_display.visible = True
            return f"Error: {str(e)}"

    async def handle_toggle(table_data) -> str:
        try:
            selected_ids = [row[0] for row in table_data if row and len(row) > 0]
            if not selected_ids:
                return "No repositories selected"
                
            if not await gr.confirm("Are you sure you want to toggle the state of selected repositories?"):
                return "Operation cancelled"
                
            for dataset_id in selected_ids:
                await repository_manager.toggle_repository_state(dataset_id)
            await refresh_status()
            return "Repository states updated successfully"
        except Exception as e:
            error_display.value = f"<div class='error-message'>{str(e)}</div>"
            error_display.visible = True
            return f"Error toggling repository states: {str(e)}"

    async def handle_delete(table_data) -> str:
        try:
            selected_ids = [row[0] for row in table_data if row and len(row) > 0]
            if not selected_ids:
                return "No repositories selected"
                
            if not await gr.confirm("Are you sure you want to delete the selected repositories?"):
                return "Operation cancelled"
                
            for dataset_id in selected_ids:
                await repository_manager.delete_repository(dataset_id)
            await refresh_status()
            return "Repositories deleted successfully"
        except Exception as e:
            error_display.value = f"<div class='error-message'>{str(e)}</div>"
            error_display.visible = True
            return f"Error deleting repositories: {str(e)}"

    add_btn.click(
        fn=handle_add_repository,
        inputs=[url_input, branch_input],
        outputs=[url_input, branch_input, status_message],
        show_progress="full"
    )
    
    refresh_btn.click(
        fn=refresh_status,
        outputs=[status_table],
        show_progress="minimal"
    )
    
    sync_btn.click(
        fn=handle_sync,
        inputs=[status_table],
        outputs=[status_message],
        show_progress="full"
    )

    toggle_btn.click(
        fn=handle_toggle,
        inputs=[status_table],
        outputs=[status_message],
        show_progress="minimal"
    )

    delete_btn.click(
        fn=handle_delete,
        inputs=[status_table],
        outputs=[status_message],
        show_progress="minimal"
    )

    demo.load(
        fn=refresh_status,
        outputs=[status_table],
        every=30
    )

    return {
        "demo": demo,
        "url_input": url_input,
        "branch_input": branch_input,
        "add_btn": add_btn,
        "refresh_btn": refresh_btn,
        "sync_btn": sync_btn,
        "toggle_btn": toggle_btn,
        "delete_btn": delete_btn,
        "status_table": status_table,
        "status_message": status_message,
        "error_display": error_display,
        "sync_status": sync_status,
        "loading_status": loading_status,
        "status_text": status_text
    }