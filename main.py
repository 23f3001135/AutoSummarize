# To run this code you need to install the following dependencies:
# pip install google-genai python-dotenv rich

from asyncio import sleep
import base64
import os

from dotenv import load_dotenv
from google import genai
from google.genai import types
import logging
from rich.logging import RichHandler
from time import sleep
from config import config


# ----------------------------------------------
# Console logging setup
# ----------------------------------------------
FORMAT = "%(message)s [%(levelname)s]"

logging.basicConfig(
    level="INFO",  # Set the overall logging level to DEBUG to see all messages.
    format=FORMAT,
    datefmt="[%X]",  # Use Rich's timestamp format.
    handlers=[RichHandler(rich_tracebacks=False)] # Added rich_tracebacks for better error handling
)

# Get a logger instance.
log = logging.getLogger("rich_logging_example")

# ----------------------------------------------
# Load environment variables from .env file
# ----------------------------------------------
# --- Added logging ---
log.debug("Loading environment variables from .env file...")
load_dotenv()
log.info("Environment variables loaded. ✅")
# ----------------------------------------------

# ----------------------------------------------
# global variables
# ----------------------------------------------
model, prompt, segment_duration = config()

def generate(fileName, prompt=prompt, model=model):
    """
    Generates content based on a prompt and a video file using the Gemini API.
    """
    log.info(f"Starting content generation process with model: '{model}'")
    
    try:
        log.info("Initializing Gemini client...")
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        log.info("Gemini client initialized successfully.")


        log.info(f"Uploading file '{fileName}' to Gemini...")
        file = client.files.upload(file=f"{fileName}")
        
        log.info(f"File uploaded successfully. File URI: {file.uri}")
        log.info(f"File details: {file}")
        log.info(f"Waiting for file '{fileName}' to be processed...")
        
        log.info("⏳ Processing, please wait...")
        # Wait for the file to be processed.
        while file.state.name != "ACTIVE":

            sleep(30)  # Wait for 10 seconds before checking again
            log.info(f"Current file state: {file.state.name}")
            if file.state.name == "FAILED":
                log.error(f"File processing failed with state: {file.state.name}")
                break
        

        file = client.files.get(name=file.name) # Get the latest status
        log.info("File is now ACTIVE and ready to use. ✅")
        
        # --- Added logging ---
        log.info("Sending request to the model for content generation...")
        
        response = client.models.generate_content(
            model=model,
            contents=[prompt, file],
            # config=generate_content_config,
        )
        
        # --- Added logging ---
        log.info("Successfully received response from the model. 🤖")
        log.debug(f"Full response object: {response}")
        
        print("\n--- Generated Summary ---")
        print(response.text)
        print("-------------------------\n")

    except Exception as e:
        log.error(f"An error occurred during the generation process: {e}", exc_info=True)

def generate_video_segments(fileName, segment_duration=segment_duration):
    """
    Generates video segments based on the specified duration.
    """
    log.info(f"Generating video segments for file '{fileName}' with segment duration of {segment_duration} seconds.")

if __name__ == "__main__":
    # Ensure the file path is correct
    filePath = os.path.join("2025-07-29 20-29-18.mp4")

    # --- Added logging ---
    log.info("Script starting...")
    if not os.path.exists(filePath):
        log.error(f"The specified file does not exist: '{filePath}'")
    elif not os.getenv("GEMINI_API_KEY"):
        log.error("GEMINI_API_KEY environment variable not found. Please set it in your .env file.")
    else:
        generate(filePath, prompt=prompt, model=model)

    log.info("Script finished.")