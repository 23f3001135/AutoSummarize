import json
import logging
import os
from pathlib import Path
from threading import Lock
from models import db, Setting as SettingModel

logger = logging.getLogger(__name__)
SETTINGS_FILE = Path("settings.json")
settings_lock = Lock()

# Default settings
DEFAULT_SETTINGS = {
    "model": "gemini-2.5-flash",
    "api_key": "",
    "summary_prompt": """
Role: You are an expert corporate summarizer specializing in professional minutes of meetings and executive summaries for senior stakeholders.
Task: Analyze the provided call recording and produce a concise, well-structured, and formal summary.
Requirements:
	•	Thoroughly review the recording; replay as needed to ensure accuracy.
	•	Capture:
	•	Meeting objective
	•	Key discussion points
	•	Decisions made
	•	Action items with owners and deadlines
	•	Participants present
	•	Follow-ups or next steps
	•	Structure the output with clear sections and bullet points where appropriate (e.g., Meeting Objective, Key Discussions, Decisions, Action Items, Next Steps).
	•	Maintain an objective, neutral tone without personal opinions or interpretation.
	•	Ensure the output is immediately suitable for corporate documentation—ready to copy into an official email or report.
	•	Prohibited: Any introductory phrases (e.g., “Here’s the summary…”), closing remarks, or meta-commentary. Start directly with the formatted summary, e.g.:
**Minutes of Meeting**
**Date:** October xx, 20xx  
**Participants:** David, Naman, ...  
	•	Replace all placeholder information (date, participants, etc.) with actual data from the recording.
    - best keep your response in markdown so we can easily format it.
""",
    "transcription_prompt": """
Role: You are a highly accurate verbatim transcription service.
Task: Transcribe the provided audio exactly as spoken.
Requirements:
	•	Capture every word exactly, including filler words (“um,” “uh”), pauses, false starts, and grammatical errors.
	•	Do not paraphrase, interpret, or summarize.
	•	Output only the raw transcript—no headings, introductions, or commentary.
	•	Prohibited: Any prefatory text such as “Here’s the transcription…” or closing remarks. The response must contain only the verbatim transcription content.
""",
    "max_duration_seconds": 3600,
}


def _load_settings_from_db():
    cfg = {}
    try:
        items = SettingModel.query.all()
        for s in items:
            try:
                cfg[s.key] = json.loads(s.value)
            except Exception:
                cfg[s.key] = s.value
    except Exception as e:
        logger.debug(f"Settings DB read failed: {e}")
    return cfg


def load_settings():
    """Load settings from DB; fall back to file, then defaults. Ensures types and defaults."""
    with settings_lock:
        # Prefer DB
        settings = _load_settings_from_db()
        if not settings:
            # Fall back to existing file to bootstrap, then migrate into DB
            try:
                if SETTINGS_FILE.exists():
                    with open(SETTINGS_FILE, "r") as f:
                        settings = json.load(f)
            except Exception as e:
                logger.debug(f"Settings file read failed: {e}")

        # Merge defaults
        merged = DEFAULT_SETTINGS.copy()
        merged.update(settings or {})

        # Coerce types
        try:
            merged["max_duration_seconds"] = int(merged.get("max_duration_seconds", DEFAULT_SETTINGS["max_duration_seconds"]))
        except (ValueError, TypeError):
            merged["max_duration_seconds"] = DEFAULT_SETTINGS["max_duration_seconds"]

        return merged


def save_settings(settings_data):
    """Persist settings to DB (JSON-serialize values)."""
    with settings_lock:
        try:
            for key, value in settings_data.items():
                # Store as JSON where possible
                try:
                    serialized = json.dumps(value)
                except Exception:
                    serialized = str(value)
                s = SettingModel.query.get(key)
                if not s:
                    s = SettingModel()
                    s.key = key
                    s.value = serialized
                    db.session.add(s)
                else:
                    s.value = serialized
            db.session.commit()
            logger.info("Settings saved to DB.")
        except Exception as e:
            logger.error(f"Failed to save settings to DB: {e}")
            raise


def get_config():
    """Get configuration values for the application (compatible with existing config.py)."""
    settings = load_settings()

    # Get API key from settings or environment (environment takes precedence)
    api_key = os.getenv("GEMINI_API_KEY") or settings.get("api_key", "")
    if api_key and not os.getenv("GEMINI_API_KEY"):
        # Set environment variable if using settings API key
        os.environ["GEMINI_API_KEY"] = api_key

    return (
        settings.get("model", DEFAULT_SETTINGS["model"]),
        settings.get("summary_prompt", DEFAULT_SETTINGS["summary_prompt"]),
        int(
            settings.get(
                "max_duration_seconds", DEFAULT_SETTINGS["max_duration_seconds"]
            )
        ),
        settings.get("transcription_prompt", DEFAULT_SETTINGS["transcription_prompt"]),
    )


def update_setting(key, value):
    """Update a single setting in DB."""
    settings = load_settings()
    settings[key] = value
    save_settings(settings)

    if key == "api_key" and value:
        os.environ["GEMINI_API_KEY"] = value
    logger.info(f"Updated setting {key} in DB")


def get_setting(key, default=None):
    """Get a single setting value."""
    settings = load_settings()
    return settings.get(key, default)
