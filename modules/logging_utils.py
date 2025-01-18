import logging
from typing import Dict, Any

async def log_request_response(request: Dict[str, Any], response: Dict[str, Any]):
    if "error" in response:
        logging.error(
            f"Error occurred: {response['type']}\n"
            f"Request: {request}\n"
            f"Error message: {response['error']}"
        )
    else:
        logging.info(f"Request: {request}\nResponse: {response}")