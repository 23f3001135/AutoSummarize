import os
import logging
import asyncio
import subprocess
from pathlib import Path
import tempfile
from concurrent.futures import ThreadPoolExecutor

# Import all necessary components
from . import gemini_processor
from settings import get_config
from google import genai

logger = logging.getLogger(__name__)


def _get_media_duration(file_path: Path) -> float:
    """
    Get the duration of a media file using FFprobe.
    Returns duration in seconds.
    """
    try:
        cmd = [
            'ffprobe', '-v', 'quiet', '-select_streams', 'a:0',
            '-show_entries', 'format=duration', '-of', 'csv=p=0',
            str(file_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        duration = float(result.stdout.strip())
        logger.info(f"Media duration for {file_path.name}: {duration:.2f}s")
        return duration
    except (subprocess.CalledProcessError, ValueError) as e:
        logger.error(f"Failed to get duration for {file_path.name}: {e}")
        raise


def _extract_audio_chunk(file_path: Path, start_time: float, duration: float, output_path: Path) -> Path:
    """
    Extract an audio chunk from a media file using FFmpeg.
    """
    try:
        cmd = [
            'ffmpeg', '-y',  # -y to overwrite output files
            '-i', str(file_path),
            '-ss', str(start_time),  # Start time
            '-t', str(duration),     # Duration
            '-vn',                   # No video
            '-acodec', 'mp3',        # Audio codec
            '-ab', '128k',           # Audio bitrate
            '-ar', '44100',          # Audio sample rate
            str(output_path)
        ]
        
        logger.info(f"Extracting chunk: {output_path.name} from {start_time}s for {duration}s")
        
        # Run FFmpeg with minimal output
        subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            check=True
        )
        
        if not output_path.exists():
            raise RuntimeError(f"FFmpeg completed but output file was not created: {output_path}")
            
        logger.info(f"Successfully created chunk: {output_path.name}")
        return output_path
        
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg failed for chunk {output_path.name}: {e.stderr}")
        raise
    except Exception as e:
        logger.error(f"Failed to extract chunk {output_path.name}: {e}")
        raise


def _write_chunk(chunk_info: tuple) -> Path:
    """
    Helper function to extract a single audio chunk using FFmpeg.
    This function will be executed in parallel threads.
    """
    file_path, start_time, duration, output_path = chunk_info
    return _extract_audio_chunk(file_path, start_time, duration, output_path)


def _split_audio(file_path: Path, segment_duration: int, output_dir: Path) -> list[Path]:
    """
    Splits a large audio or video file into smaller audio chunks using FFmpeg.
    Attempts multithreading first, falls back to sequential processing if needed.
    """
    logger.info(f"Splitting '{file_path.name}' into {segment_duration}-second audio chunks using FFmpeg.")
    
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # First, try multithreaded approach
        try:
            return _split_audio_multithreaded(file_path, segment_duration, output_dir)
        except Exception as e:
            logger.warning(f"Multithreaded splitting failed: {e}. Falling back to sequential processing...")
            # Clean up any partial chunks from failed multithreaded attempt
            for p in output_dir.glob(f"{file_path.stem}_chunk_*.mp3"):
                if p.exists():
                    p.unlink()
            # Fall back to sequential processing
            return _split_audio_sequential(file_path, segment_duration, output_dir)
            
    except Exception as e:
        logger.error(f"Failed to split file {file_path.name}: {e}", exc_info=True)
        # Clean up any created chunks if splitting fails
        for p in output_dir.glob(f"{file_path.stem}_chunk_*.mp3"):
            if p.exists():
                p.unlink()
        raise


def _split_audio_multithreaded(file_path: Path, segment_duration: int, output_dir: Path) -> list[Path]:
    """
    Attempts to split audio using multithreading for faster processing with FFmpeg.
    """
    logger.info(f"Attempting multithreaded FFmpeg splitting for '{file_path.name}'...")
    
    # Get the media duration using FFprobe
    duration = _get_media_duration(file_path)
    
    # Prepare all chunks data first
    chunk_tasks = []
    chunk_paths = []
    for i in range(0, int(duration), segment_duration):
        start_time = i
        chunk_duration = min(segment_duration, duration - i)
        chunk_name = f"{file_path.stem}_chunk_{i // segment_duration + 1}.mp3"
        chunk_path = output_dir / chunk_name
        
        logger.info(f"Preparing chunk: {chunk_path.name} from {start_time}s for {chunk_duration}s")
        chunk_tasks.append((file_path, start_time, chunk_duration, chunk_path))
        chunk_paths.append(chunk_path)
    
    logger.info(f"Created {len(chunk_tasks)} chunk tasks. Now processing them in parallel...")
    
    # Use ThreadPoolExecutor to process chunks in parallel
    # Use max 4 workers to avoid overwhelming the system
    max_workers = min(4, len(chunk_tasks))
    completed_paths = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all chunk extraction tasks
        future_to_chunk = {
            executor.submit(_write_chunk, chunk_task): chunk_task[3]  # chunk_task[3] is the output path
            for chunk_task in chunk_tasks
        }
        
        # Collect results as they complete
        for future in future_to_chunk:
            chunk_path = future.result()  # This will raise if any chunk failed
            completed_paths.append(chunk_path)

    logger.info(f"Successfully split '{file_path.name}' into {len(completed_paths)} chunks using multithreaded FFmpeg.")
    return sorted(completed_paths)  # Sort to maintain order


def _split_audio_sequential(file_path: Path, segment_duration: int, output_dir: Path) -> list[Path]:
    """
    Splits audio sequentially using FFmpeg - slower but more reliable for problematic files.
    """
    logger.info(f"Using sequential FFmpeg splitting for '{file_path.name}'...")
    
    chunk_paths = []
    
    # Get the media duration using FFprobe
    duration = _get_media_duration(file_path)
    
    for i in range(0, int(duration), segment_duration):
        start_time = i
        chunk_duration = min(segment_duration, duration - i)
        chunk_name = f"{file_path.stem}_chunk_{i // segment_duration + 1}.mp3"
        chunk_path = output_dir / chunk_name
        
        logger.info(f"Creating chunk: {chunk_path.name} from {start_time}s for {chunk_duration}s")
        
        # Extract chunk using FFmpeg
        _extract_audio_chunk(file_path, start_time, chunk_duration, chunk_path)
        chunk_paths.append(chunk_path)

    logger.info(f"Successfully split '{file_path.name}' into {len(chunk_paths)} chunks using sequential FFmpeg.")
    return chunk_paths


def process_single_file(file_path: Path, progress_callback=None) -> dict:
    """
    Processes a single file. If the file's duration is too long, it splits
    it into chunks, transcribes them, and then summarizes the combined transcript.
    For short files, it transcribes and then summarizes.
    Returns a dictionary with 'summary' and 'transcript'.
    
    Args:
        file_path: Path to the media file
        progress_callback: Optional callback function(progress, message) to report progress
    """
    logger.info(f"Starting single file processing for: {file_path}")
    
    def update_progress(progress, message):
        if progress_callback:
            progress_callback(progress, message)
    
    # Unpack all config values
    model, summary_prompt, max_duration_seconds, transcription_prompt = get_config()
    
    try:
        # We need a new async main function to orchestrate the async calls
        async def main():
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("GEMINI_API_KEY not found in environment.")
            client = genai.Client(api_key=api_key)

            update_progress(10, '✅ Upload complete, validating file...')

            # Get media duration using FFprobe
            duration = _get_media_duration(file_path)
            
            update_progress(20, '🔍 Analyzing file format and size...')

            if duration <= max_duration_seconds:
                # --- Short File Workflow ---
                logger.info(f"File duration ({duration:.2f}s) is under the limit. Processing directly.")
                
                update_progress(30, '🚀 Sending to Google AI for processing...')
                
                # 1. Transcribe the whole file
                logger.info("Transcribing the full short file...")
                # Note: We use transcribe_chunk_async here as it handles the full upload/process/delete cycle for a single file.
                transcript_text = await gemini_processor.transcribe_chunk_async(client, model, transcription_prompt, file_path)
                
                update_progress(70, '🤖 AI finished transcription, generating summary...')

                if not transcript_text:
                    raise ValueError("Transcription returned an empty result.")

                # 2. Summarize the transcript
                logger.info("Summarizing the transcript...")
                update_progress(90, '📝 Finalizing summary...')
                summary_text = await gemini_processor.generate_async(
                    model=model,
                    prompt=summary_prompt,
                    transcript_text=transcript_text
                )
                update_progress(95, '🎉 Almost done, preparing results...')
                return {"summary": summary_text, "transcript": transcript_text}
            else:
                # --- Long File Workflow ---
                logger.info(f"File duration ({duration:.2f}s) exceeds the limit. Starting chunking process.")
                
                update_progress(25, '✂️ Splitting large file into chunks...')
                
                with tempfile.TemporaryDirectory() as temp_dir:
                    chunk_output_dir = Path(temp_dir)
                    
                    # 1. Split the audio into chunks
                    logger.info("Splitting audio into chunks...")
                    chunk_paths = _split_audio(file_path, max_duration_seconds, chunk_output_dir)
                    
                    if not chunk_paths:
                        raise ValueError("File splitting resulted in no chunks.")

                    update_progress(35, f'🚀 Processing {len(chunk_paths)} chunks with AI...')

                    # 2. Transcribe each chunk sequentially
                    logger.info(f"Transcribing {len(chunk_paths)} chunks sequentially...")
                    
                    transcripts = []
                    for i, chunk in enumerate(chunk_paths):
                        chunk_progress = 35 + (i / len(chunk_paths)) * 50  # 35% to 85%
                        update_progress(int(chunk_progress), f'🤖 Processing chunk {i+1}/{len(chunk_paths)}...')
                        
                        logger.info(f"Transcribing chunk {i+1}/{len(chunk_paths)}...")
                        transcript = await gemini_processor.transcribe_chunk_async(client, model, transcription_prompt, chunk)
                        transcripts.append(transcript)
                        if i < len(chunk_paths) - 1:
                            logger.info("Waiting for 6 seconds before next transcription request...")
                            await asyncio.sleep(6)
                    
                    full_transcript = "\n".join(transcripts)
                    
                    if not full_transcript:
                        raise ValueError("Transcription of chunks returned an empty result.")

                    update_progress(85, '📝 All chunks processed, generating final summary...')
                    logger.info("All chunks transcribed. Generating final summary from transcript.")

                    # 3. Generate the final summary from the combined transcript
                    final_summary = await gemini_processor.generate_async(
                        model=model,
                        prompt=summary_prompt,
                        transcript_text=full_transcript
                    )
                    
                    update_progress(95, '🎉 Almost done, preparing results...')

                    return {"summary": final_summary, "transcript": full_transcript}

        # Run the main async orchestrator
        result = asyncio.run(main())
        logger.info(f"Successfully generated summary and transcript for {file_path.name}")
        return result

    except Exception as e:
        logger.error(f"Error processing {file_path.name}: {e}", exc_info=True)
        return {"summary": f"An error occurred during processing: {e}", "transcript": None}
