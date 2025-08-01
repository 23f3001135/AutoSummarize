# ==============================================================================
# File: processing/gemini_processor.py
# Description: Contains the async Gemini API logic.
# ==============================================================================
import os
import asyncio
import logging
from pathlib import Path

from google import genai
from dotenv import load_dotenv

# Load environment variables at the module level
load_dotenv()
logger = logging.getLogger(__name__)

async def generate(fileName: Path, prompt: str, model: str) -> str:
    """
    Generates content based on a prompt and a file using the Gemini API.
    """
    logger.info(f"Starting async content generation with model: '{model}'")
    
    # Configure the Gemini client with the API key
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in environment variables.")
    genai.configure(api_key=api_key)

    logger.info(f"Uploading file '{fileName}' to Gemini...")
    # The SDK's upload_file is synchronous, so we run it in a separate thread
    # to avoid blocking the asyncio event loop.
    file = await asyncio.to_thread(genai.upload_file, path=fileName)
    logger.info(f"File uploaded successfully. URI: {file.uri}")

    try:
        logger.info("Waiting for file to be processed...")
        while file.state.name == "PROCESSING":
            await asyncio.sleep(10) # Non-blocking sleep
            file = await asyncio.to_thread(genai.get_file, name=file.name)
            logger.info(f"Current file state: {file.state.name}")

        if file.state.name == "FAILED":
            logger.error(f"File processing failed. State: {file.state.name}")
            raise ValueError("Gemini API failed to process the file.")
        
        logger.info("File is now ACTIVE and ready to use. ✅")
        
        generation_model = genai.GenerativeModel(model_name=model)
        logger.info("Sending request to the model for content generation...")
        
        response = await asyncio.to_thread(
            generation_model.generate_content,
            [prompt, file],
        )
        
        logger.info("Successfully received response from the model. 🤖")
        return response.text

    finally:
        # Ensure the file is deleted from Gemini's servers even if an error occurs
        logger.info(f"Deleting file {file.name} from Gemini server...")
        await asyncio.to_thread(genai.delete_file, name=file.name)
        logger.info("Gemini file deleted.")
