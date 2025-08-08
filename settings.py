import json
import logging
import os
from pathlib import Path
from threading import Lock

logger = logging.getLogger(__name__)
SETTINGS_FILE = Path("settings.json")
settings_lock = Lock()

# Default settings
DEFAULT_SETTINGS = {
    "model": "gemini-2.5-flash",
    "api_key": "",
    "summary_prompt": """You are an expert summarizer specializing in crafting professional minutes of meetings and executive summaries. Please analyze the following call recording and generate a concise, well-structured, and formal summary. Ensure the output reflects a tone appropriate for stakeholders or senior management.
Instructions: 
Review the video thoroughly; feel free to replay it multiple times to ensure complete understanding.
Focus on capturing key discussion points, decisions made, action items, participants involved, and any timelines or follow-ups discussed.
Structure the summary in a clear, professional format — ideally with bullet points or short sections under headers (e.g., Meeting Objective, Key Discussions, Decisions, Action Items, Next Steps).
Maintain an objective tone and avoid subjective interpretation.
Output Format: Provide the summary in a clean and professional style suitable for corporate documentation or official records. Important: avoid writting things like "Here's the minutes of the meeting as per your request which is professionally written" instead directly write what's asked and also avoid ending statements such as "Let me know if you'd like a lighter version for internal use or a template for recurring use across meetings." or anything similar your response will directly be copy pasted in docs and emailed to c-suite executives, so it should be ready to use without further editing.
pls make sure to avoid writing things like "Certainly. Here's a summary of the call recording: ..." stright 
"**Call Summary**
**Date:** October 26, 2023
**Participants:** David, Aman
"
this was an example, it could be starting as minutes of meeting. or somerhign which sounds good.""",
    "transcription_prompt": """You are a highly accurate audio transcription service. Your task is to transcribe the provided audio segment word-for-word.
- Do not add any commentary, interpretation, or summary.
- Preserve the exact wording, including filler words (e.g., "um," "uh"), pauses, and grammatical errors.
- The output should be only the raw text of the speech from the audio.
- Stricktly do not output things like "Here's the transcription of the audio segment: \"""",
    "max_duration_seconds": 3600
}

def load_settings():
    """Load settings from settings.json file."""
    with settings_lock:
        try:
            if SETTINGS_FILE.exists():
                with open(SETTINGS_FILE, "r") as f:
                    settings = json.load(f)
                    # Ensure all default keys exist
                    for key, value in DEFAULT_SETTINGS.items():
                        if key not in settings:
                            settings[key] = value
                    
                    # Ensure numeric values are properly typed
                    if 'max_duration_seconds' in settings:
                        try:
                            settings['max_duration_seconds'] = int(settings['max_duration_seconds'])
                        except (ValueError, TypeError):
                            logger.warning(f"Invalid max_duration_seconds value, using default: {DEFAULT_SETTINGS['max_duration_seconds']}")
                            settings['max_duration_seconds'] = DEFAULT_SETTINGS['max_duration_seconds']
                    
                    return settings
            else:
                # Create default settings file
                save_settings(DEFAULT_SETTINGS)
                return DEFAULT_SETTINGS.copy()
        except Exception as e:
            logger.error(f"Failed to load settings: {e}. Using defaults.")
            return DEFAULT_SETTINGS.copy()

def save_settings(settings_data):
    """Save settings to settings.json file."""
    with settings_lock:
        try:
            with open(SETTINGS_FILE, "w") as f:
                json.dump(settings_data, f, indent=4)
            logger.info("Settings saved successfully.")
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
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
        int(settings.get("max_duration_seconds", DEFAULT_SETTINGS["max_duration_seconds"])),
        settings.get("transcription_prompt", DEFAULT_SETTINGS["transcription_prompt"])
    )

def update_setting(key, value):
    """Update a single setting."""
    settings = load_settings()
    settings[key] = value
    save_settings(settings)
    
    # If updating API key, also update environment variable
    if key == "api_key" and value:
        os.environ["GEMINI_API_KEY"] = value
    
    logger.info(f"Updated setting {key}")

def get_setting(key, default=None):
    """Get a single setting value."""
    settings = load_settings()
    return settings.get(key, default)
