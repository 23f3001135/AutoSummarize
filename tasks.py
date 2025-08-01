import os
from pathlib import Path
import logging
from celery import Celery
# Removed database import as it's no longer needed
from processing.media_handler import process_single_file

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configure Celery to use Redis as the message broker and result backend
celery_app = Celery('tasks', broker='redis://localhost:6379/0', backend='redis://localhost:6379/0')

@celery_app.task
def summarize_task(file_path_str: str):
    """
    The background task that performs the summarization.
    It no longer interacts with a database. It simply returns the
    result or raises an exception, which Celery stores in the backend.
    """
    file_path = Path(file_path_str)
    
    try:
        logger.info(f"Task {summarize_task.request.id}: Starting processing for {file_path.name}")
        
        # Run the core summarization logic
        summary_text = process_single_file(file_path)

        if not summary_text:
            raise ValueError("Processing returned an empty summary.")
        
        logger.info(f"Task {summarize_task.request.id}: Successfully generated summary.")
        # Return the result. Celery will store this and set status to SUCCESS.
        return summary_text

    except Exception as e:
        # If an error occurs, re-raising it will cause Celery to
        # mark the task as FAILED and store the exception as the result.
        logger.error(f"Task {summarize_task.request.id}: An error occurred: {e}", exc_info=True)
        raise e
    finally:
        # Ensure the temporary file is always cleaned up
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Task {summarize_task.request.id}: Cleaned up temporary file: {file_path.name}")
