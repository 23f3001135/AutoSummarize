import os
import logging
import asyncio
from pathlib import Path
from typing import Optional, Any

from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# --- Main Orchestrator Function ---

async def generate_async(
    model: str, 
    prompt: str, 
    file_path: Optional[Path] = None, 
    transcript_text: Optional[str] = None,
    client: Optional[genai.Client] = None
) -> str:
    """
    Orchestrates the entire generation process asynchronously.
    Can generate content based on a file upload or on pre-existing text.
    If a client is not provided, it will be created.
    """
    if not file_path and not transcript_text:
        raise ValueError("Either file_path or transcript_text must be provided.")

    # Create a client if one isn't passed
    if not client:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables.")
        client = genai.Client(api_key=api_key)

    file: Optional[types.File] = None
    try:
        if file_path:
            # Scenario 1: Generate from a file
            logger.info(f"Starting content generation for '{file_path.name}' with model '{model}'")
            file = await _upload_file_async(client, file_path)
            file = await _wait_for_processing_async(client, file)
            content = await _generate_content_async(client, model, prompt, file=file)
        else:
            # Scenario 2: Generate from a transcript
            logger.info(f"Starting content generation from text with model '{model}'")
            content = await _generate_content_async(client, model, prompt, text_content=transcript_text)
        
        return content

    except Exception as e:
        logger.error(f"An error occurred during the generation process: {e}", exc_info=True)
        raise e
        
    finally:
        # Clean up the file on the Gemini server if one was uploaded
        if file:
            logger.info(f"Deleting file {file.name} from Gemini server...")
            client.files.delete(name=file.name)
            logger.info(f"File {file.name} deleted successfully.")

# --- Helper Functions ---

async def _upload_file_async(client: genai.Client, file_path: Path) -> types.File:
    """
    Uploads a file asynchronously to the Gemini server.
    """
    logger.info(f"Starting async file upload for: {file_path.name}")
    file = client.files.upload(file=file_path)
    logger.info(f"Async upload complete for {file_path.name}. URI: {file.uri}")
    return file

async def _wait_for_processing_async(client: genai.Client, file: types.File) -> types.File:
    """
    Waits asynchronously for the file to become ACTIVE.
    """
    logger.info(f"Waiting for file '{file.name}' to be processed...")
    while file.state.name == "PROCESSING":
        await asyncio.sleep(5)
        file = client.files.get(name=file.name)
        logger.info(f"Current file state for '{file.name}': {file.state.name}")

    if file.state.name == "FAILED":
        logger.error(f"File processing failed: {file.error}")
        raise ValueError(f"File processing failed: {file.error}")

    if file.state.name == "ACTIVE":
        logger.info(f"File '{file.name}' is now ACTIVE and ready to use. ✅")
        return file
    else:
        logger.error(f"Unexpected file state: {file.state.name}")
        raise ValueError(f"Unexpected file state: {file.state.name}")

async def _generate_content_async(
    client: genai.Client, 
    model: str, 
    prompt: str, 
    file: Optional[types.File] = None, 
    text_content: Optional[str] = None
) -> str:
    """
    Generates content asynchronously from either a processed file or raw text.
    """
    logger.info("Sending request to the model for content generation...")
    
    contents: list[Any] = [prompt]
    if file:
        contents.append(file)
    elif text_content:
        contents.append(text_content)
    else:
        raise ValueError("Either a file or text_content must be provided.")

    response = client.models.generate_content(
        model=model,
        contents=contents,
    )
    logger.info("Successfully received response from the model. 🤖")
    logger.debug(f"Full response object: {response}")
    return response.text or ""

async def transcribe_chunk_async(client: genai.Client, model: str, prompt: str, chunk_path: Path) -> str:
    """
    A wrapper around generate_async specifically for transcribing a single file chunk.
    It uploads the chunk, generates the transcript, and handles cleanup.
    """
    logger.info(f"Transcribing chunk: {chunk_path.name}")
    # Re-use the main async generator, passing the client and file path
    transcript = await generate_async(
        model=model,
        prompt=prompt,
        file_path=chunk_path,
        client=client # Pass the existing client to avoid re-creating it
    )
    logger.info(f"Successfully transcribed chunk: {chunk_path.name}")
    return transcript
