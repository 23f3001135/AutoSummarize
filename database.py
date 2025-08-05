import json
import logging
from pathlib import Path
from threading import Lock

logger = logging.getLogger(__name__)
HISTORY_FILE = Path("history.json")
db_lock = Lock()

def save_job(job_data: dict):
    """Appends a single completed job to the history.json file."""
    with db_lock:
        logger.info(f"Persisting job {job_data.get('id')} to {HISTORY_FILE}")
        try:
            if HISTORY_FILE.exists():
                with open(HISTORY_FILE, "r+") as f:
                    history = json.load(f)
                    history[job_data['id']] = job_data
                    f.seek(0)
                    json.dump(history, f, indent=4)
            else:
                with open(HISTORY_FILE, "w") as f:
                    json.dump({job_data['id']: job_data}, f, indent=4)
            logger.info(f"Successfully saved job {job_data.get('id')}.")
        except Exception as e:
            logger.error(f"Failed to save job {job_data.get('id')} to {HISTORY_FILE}: {e}", exc_info=True)

def load_all_jobs() -> dict:
    """Loads all jobs from the history.json file."""
    with db_lock:
        if not HISTORY_FILE.exists():
            logger.warning(f"{HISTORY_FILE} not found. Starting with an empty history.")
            return {}
        try:
            with open(HISTORY_FILE, "r") as f:
                history = json.load(f)
                logger.info(f"Successfully loaded {len(history)} jobs from {HISTORY_FILE}.")
                return history
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to load or parse {HISTORY_FILE}: {e}. Starting fresh.", exc_info=True)
            return {}
