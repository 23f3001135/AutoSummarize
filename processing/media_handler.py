import logging
import asyncio
from pathlib import Path
from .gemini_processor import generate_async as generate_summary
from config import config

logger = logging.getLogger(__name__)

def process_single_file(file_path: Path) -> str:
    """Processes a single file by running the async generation function."""
    logger.info(f"Starting single file processing for: {file_path}")
    model, prompt, _ = config()
    try:
        # Run the async function from a sync context
        summary = asyncio.run(generate_summary(file_path, prompt, model))
        logger.info(f"Successfully generated summary for {file_path}")
        return summary
    except Exception as e:
        logger.error(f"Error processing {file_path}: {e}", exc_info=True)
        # Depending on desired error handling, you might return an error message
        # or re-raise the exception. For now, returning an empty string.
        return ""
