import os
import logging
import asyncio
from pathlib import Path
from moviepy import AudioFileClip

# Import all necessary components
from . import gemini_processor
from . import media_splitter
from config import config
from google import genai
import tempfile

logger = logging.getLogger(__name__)

def process_single_file(file_path: Path) -> str:
    """
    Processes a single file. If the file's duration is too long, it splits 
    it into chunks, transcribes them, and then summarizes the combined transcript.
    """
    logger.info(f"Starting single file processing for: {file_path}")
    
    # Unpack all config values based on the new duration-based logic
    model, summary_prompt, max_duration_seconds, transcription_prompt = config()
    
    try:
        # Get the duration of the media file first
        with AudioFileClip(str(file_path)) as media:
            duration = media.duration

        # We need a new async main function to orchestrate the async calls
        async def main():
            if duration <= max_duration_seconds:
                # --- Short File Workflow ---
                logger.info(f"File duration ({duration:.2f}s) is under the limit. Processing directly.")
                return await gemini_processor.generate_async(
                    model=model,
                    prompt=summary_prompt,
                    file_path=file_path
                )
            else:
                # --- Long File Workflow ---
                logger.info(f"File duration ({duration:.2f}s) exceeds the limit. Starting chunking process.")
                
                # Define a directory to store the chunks
                chunk_output_dir = file_path.parent / f"{file_path.stem}_chunks"
                
                # 1. Split the audio into chunks based on the max_duration_seconds
                chunk_paths = media_splitter.split_audio(file_path, max_duration_seconds, chunk_output_dir)
                
                if not chunk_paths:
                    raise ValueError("File splitting resulted in no chunks.")

                # 2. Transcribe each chunk in parallel
                logger.info(f"Transcribing {len(chunk_paths)} chunks in parallel...")
                
                # We need a client instance for the transcription calls
                api_key = os.getenv("GEMINI_API_KEY")
                if not api_key:
                    raise ValueError("GEMINI_API_KEY not found for transcription.")
                client = genai.Client(api_key=api_key)

                transcription_tasks = [
                    gemini_processor.transcribe_chunk_async(client, model, transcription_prompt, chunk)
                    for chunk in chunk_paths
                ]
                
                transcripts = await asyncio.gather(*transcription_tasks)
                full_transcript = "\n".join(transcripts)
                
                logger.info("All chunks transcribed. Generating final summary from transcript.")

                # 3. Generate the final summary from the combined transcript
                final_summary = await gemini_processor.generate_async(
                    model=model,
                    prompt=summary_prompt,
                    transcript_text=full_transcript
                )

                # 4. Clean up the local chunk files
                logger.info("Cleaning up temporary audio chunks...")
                for chunk in chunk_paths:
                    if chunk.exists():
                        chunk.unlink()
                if chunk_output_dir.exists() and not any(chunk_output_dir.iterdir()):
                    chunk_output_dir.rmdir()

                return final_summary

        # Run the main async orchestrator
        summary = asyncio.run(main())
        logger.info(f"Successfully generated summary for {file_path.name}")
        return summary

    except Exception as e:
        logger.error(f"Error processing {file_path.name}: {e}", exc_info=True)
        return f"An error occurred during processing: {e}"
