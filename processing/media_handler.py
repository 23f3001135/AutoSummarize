import logging
from pathlib import Path
from .gemini_processor import generate as generate_summary
from config import config

logger = logging.getLogger(__name__)

async def process_single_file(file_path: Path) -> str:
    """
    For Phase 1, this function directly calls the Gemini processor.
    """
    logger.info(f"Starting single file processing for: {file_path}")
    
    model, prompt, _ = config()
    
    try:
        summary = await generate_summary(file_path, prompt, model)
        logger.info(f"Successfully generated summary for {file_path}")
        return summary
    except Exception as e:
        logger.error(f"Failed to generate summary for {file_path}: {e}", exc_info=True)
        # Propagate the error to be handled by the Flask route
        raise e