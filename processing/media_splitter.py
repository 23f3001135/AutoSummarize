import logging
from pathlib import Path

from moviepy import AudioFileClip

logger = logging.getLogger(__name__)

def split_audio(file_path: Path, segment_duration: int, output_dir: Path) -> list[Path]:
    """
    Splits a large audio or video file into smaller audio chunks.

    Args:
        file_path: The path to the media file.
        segment_duration: The duration of each chunk in seconds.
        output_dir: The directory to save the audio chunks.

    Returns:
        A list of paths to the generated audio chunks.
    """
    logger.info(f"Splitting '{file_path.name}' into {segment_duration}-second audio chunks.")
    
    try:
        # Create the output directory if it doesn't exist
        output_dir.mkdir(parents=True, exist_ok=True)

        # Use moviepy to handle both audio and video files
        with AudioFileClip(str(file_path)) as audio:
            duration = audio.duration
            chunk_paths = []
            
            for i in range(0, int(duration), segment_duration):
                start_time = i
                end_time = min(i + segment_duration, duration)
                
                # Define a unique name for each chunk
                chunk_name = f"{file_path.stem}_chunk_{i // segment_duration + 1}.mp3"
                chunk_path = output_dir / chunk_name
                
                logger.info(f"Creating chunk: {chunk_path.name} from {start_time}s to {end_time}s")
                
                # Create the subclip and write it to a file
                subclip = audio.subclipped(start_time, end_time)
                # Suppress moviepy logger for cleaner output and use a standard codec
                subclip.write_audiofile(str(chunk_path), codec='mp3', logger=None)
                
                chunk_paths.append(chunk_path)

        logger.info(f"Successfully split '{file_path.name}' into {len(chunk_paths)} chunks.")
        return chunk_paths

    except Exception as e:
        logger.error(f"Failed to split file {file_path.name}: {e}", exc_info=True)
        # Clean up any created chunks if splitting fails
        for p in output_dir.glob(f"{file_path.stem}_chunk_*.mp3"):
            if p.exists():
                p.unlink()
        raise
