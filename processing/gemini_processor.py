import os
import logging
import asyncio
from pathlib import Path
from typing import Optional, Any, Callable

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
    client: Optional[genai.Client] = None,
    status_cb: Optional[Callable[[str], None]] = None
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
            if status_cb:
                status_cb("🤖 Contacting model with file...")
            file = await _upload_file_async(client, file_path)
            file = await _wait_for_processing_async(client, file)
            content = await _generate_content_async(client, model, prompt, file=file, status_cb=status_cb)
        else:
            # Scenario 2: Generate from a transcript
            logger.info(f"Starting content generation from text with model '{model}'")
            if status_cb:
                status_cb("🤖 Contacting model with transcript...")
            content = await _generate_content_async(client, model, prompt, text_content=transcript_text, status_cb=status_cb)
        
        return content

    except Exception as e:
        logger.error(f"An error occurred during the generation process: {e}", exc_info=True)
        raise e
        
    finally:
        # Clean up the file on the Gemini server if one was uploaded
        if file and getattr(file, 'name', None):
            logger.info(f"Deleting file {file.name} from Gemini server...")
            try:
                remote_name = file.name or ""
                if remote_name:
                    client.files.delete(name=remote_name)
                logger.info(f"File {file.name} deleted successfully.")
            except Exception as delete_err:
                logger.warning(f"Failed to delete remote file {getattr(file, 'name', 'unknown')}: {delete_err}")

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
    while getattr(file, 'state', None) and getattr(file.state, 'name', None) == "PROCESSING":
        await asyncio.sleep(5)
        file_name = getattr(file, 'name', None)
        if not file_name:
            break
        file = client.files.get(name=file_name)
        logger.info(f"Current file state for '{getattr(file, 'name', 'unknown')}': {getattr(getattr(file, 'state', None), 'name', 'unknown')}")

    if getattr(file, 'state', None) and getattr(file.state, 'name', None) == "FAILED":
        logger.error(f"File processing failed: {file.error}")
        raise ValueError(f"File processing failed: {file.error}")

    if getattr(file, 'state', None) and getattr(file.state, 'name', None) == "ACTIVE":
        logger.info(f"File '{file.name}' is now ACTIVE and ready to use. ✅")
        return file
    else:
        state_name = getattr(getattr(file, 'state', None), 'name', 'unknown')
        logger.error(f"Unexpected file state: {state_name}")
        raise ValueError(f"Unexpected file state: {state_name}")

async def _generate_content_async(
    client: genai.Client, 
    model: str, 
    prompt: str, 
    file: Optional[types.File] = None, 
    text_content: Optional[str] = None,
    status_cb: Optional[Callable[[str], None]] = None
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

    # Exponential backoff for transient errors
    max_attempts = 5
    base_delay = 2
    last_err = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
            )
            logger.info("Successfully received response from the model. 🤖")
            logger.debug(f"Full response object: {response}")
            return response.text or ""
        except Exception as e:
            last_err = e
            # Detect potentially retryable errors by message/code if available
            msg = str(e)
            retryable = any(code in msg for code in ["429", "500", "502", "503", "504", "timeout", "temporarily unavailable"]) or True
            if attempt < max_attempts and retryable:
                delay = base_delay * (2 ** (attempt - 1))
                jitter = min(1.0, delay * 0.1)
                import random
                import asyncio as _asyncio
                sleep_for = delay + random.uniform(0, jitter)
                logger.warning(f"Model call failed (attempt {attempt}/{max_attempts}). Retrying in {sleep_for:.1f}s... Error: {e}")
                if status_cb:
                    status_cb(f"⏳ Model retry {attempt}/{max_attempts} in {sleep_for:.1f}s...")
                await _asyncio.sleep(sleep_for)
                continue
            logger.error(f"Model call failed and will not be retried (attempt {attempt}). Error: {e}")
            raise
    # If the loop exits without return, raise the last error
    raise last_err if last_err else RuntimeError("Model call failed with unknown error")

async def transcribe_chunk_async(client: genai.Client, model: str, prompt: str, chunk_path: Path, status_cb: Optional[Callable[[str], None]] = None) -> str:
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
        client=client, # Pass the existing client to avoid re-creating it
        status_cb=status_cb
    )
    logger.info(f"Successfully transcribed chunk: {chunk_path.name}")
    return transcript
