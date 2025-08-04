import os
import logging
import asyncio
from pathlib import Path
# Corrected import based on the new SDK guidelines
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# --- New Modular Functions ---

async def _upload_file_async(client: genai.Client, file_path: Path) -> types.File:
    """
    Uploads a file asynchronously to the Gemini server.
    """
    logger.info(f"Starting async file upload for: {file_path.name}")
    # Corrected to use the asynchronous 'a_upload' method
    file = client.files.upload(file=file_path)
    logger.info(f"Async upload complete for {file_path.name}. URI: {file.uri}")
    return file

async def _wait_for_processing_async(client: genai.Client, file: types.File) -> types.File:
    """
    Waits asynchronously for the file to become ACTIVE.
    """
    logger.info(f"Waiting for file '{file.name}' to be processed...")
    while file.state.name == "PROCESSING":
        await asyncio.sleep(5)  # Non-blocking wait
        # Get the latest status of the file asynchronously
        file = client.files.get(name=file.name)
        logger.info(f"Current file state for '{file.name}': {file.state.name}")

    if file.state.name == "FAILED":
        logger.error(f"File processing failed: {file.error}")
        raise ValueError(f"File processing failed: {file.error}")

    if file.state.name == "ACTIVE":
        logger.info(f"File '{file.name}' is now ACTIVE and ready to use. ✅")
    return file

async def _generate_content_async(client: genai.Client, model: str, prompt: str, file: types.File) -> str:
    """
    Generates the summary content asynchronously using the processed file.
    """
    logger.info("Sending request to the model for content generation...")
    # Generate content asynchronously
    response = client.models.generate_content(
        model=model,
        contents=[prompt, file],
    )
    logger.info("Successfully received response from the model. 🤖")
    logger.debug(f"Full response object: {response}")
    return response.text

# --- Main Orchestrator Function ---

async def generate_async(fileName: Path, prompt: str, model: str) -> str:
    """
    Orchestrates the entire summarization process asynchronously.
    """
    logger.info(f"Starting content generation process for '{fileName.name}' with model '{model}'")
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in environment variables.")
        
    client = genai.Client(api_key=api_key)
    file = None

    try:
        # Step 1: Upload the file asynchronously
        file = await _upload_file_async(client, fileName)

        # Step 2: Wait for the file to be processed asynchronously
        file = await _wait_for_processing_async(client, file)

        # Step 3: Generate the summary asynchronously
        summary = await _generate_content_async(client, model, prompt, file)
        return summary

    except Exception as e:
        logger.error(f"An error occurred during the generation process: {e}", exc_info=True)
        raise e
        
    finally:
        # Step 4: Clean up the file on the Gemini server asynchronously
        if file:
            logger.info(f"Deleting file {file.name} from Gemini server...")
            client.files.delete(name=file.name)
            logger.info(f"File {file.name} deleted successfully.")
