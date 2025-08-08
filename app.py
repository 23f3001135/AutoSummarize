import os
import uuid
import logging
from pathlib import Path
from threading import Lock
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge

# The processing logic is now imported directly
from processing.media_handler import process_single_file
import database
import settings

# --- New In-Memory Setup ---
# A thread-safe dictionary to store job status and results
# Load existing jobs from the database on startup
jobs = database.load_all_jobs()
jobs_lock = Lock()

# A thread pool to run summarization tasks in the background
executor = ThreadPoolExecutor(max_workers=2)
# --- End of New Setup ---

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'temporary_uploads'
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024 * 5  # 5 Gigabytes
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # Disable caching for development
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 hour

# Configure timeouts for large file processing
app.config['TIMEOUT'] = 3600  # 1 hour timeout for requests

Path(app.config['UPLOAD_FOLDER']).mkdir(parents=True, exist_ok=True)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def update_job_progress(job_id, progress, message):
    """Update job progress and status message."""
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id]['progress'] = progress
            jobs[job_id]['status_message'] = message
    logger.info(f"Job {job_id}: Progress {progress}% - {message}")

def run_summarization_task(job_id, file_path_str):
    """The function that will run in a background thread."""
    file_path = Path(file_path_str)
    logger.info(f"Job {job_id}: Starting processing for {file_path.name}")
    import time
    job_start = time.monotonic()
    
    try:
        # Set initial status
        with jobs_lock:
            jobs[job_id]['status'] = 'PROCESSING'
            jobs[job_id]['progress'] = 0
            jobs[job_id]['status_message'] = 'Starting upload...'

        # Update progress through different stages
        update_job_progress(job_id, 5, '📤 Uploading file...')
        
        # This is the long-running call to the Gemini API
        result_data = process_single_file(file_path, lambda p, m: update_job_progress(job_id, p, m))

        if not result_data or not result_data.get('summary'):
            raise ValueError("Processing returned no summary.")

        # Final progress update
        update_job_progress(job_id, 100, '🎉 Processing complete!')

        # Store the successful result with completion timestamp
        from datetime import datetime
        with jobs_lock:
            jobs[job_id]['status'] = 'COMPLETED'
            jobs[job_id]['summary'] = result_data['summary']
            jobs[job_id]['transcript'] = result_data.get('transcript')
            jobs[job_id]['progress'] = 100
            jobs[job_id]['completed_at'] = datetime.now().isoformat()
            # Prepare job data for saving
            job_to_save = jobs[job_id].copy()
        
        database.save_job(job_to_save)
        logger.info(f"Job {job_id}: Successfully generated and saved summary and transcript.")

    except Exception as e:
        # Store the failure result with completion timestamp
        logger.error(f"Job {job_id}: An error occurred: {e}", exc_info=True)
        from datetime import datetime
        with jobs_lock:
            jobs[job_id]['status'] = 'FAILED'
            jobs[job_id]['error'] = str(e)
            jobs[job_id]['completed_at'] = datetime.now().isoformat()
            # Save failed job to history
            job_to_save = jobs[job_id].copy()
        
        try:
            database.save_job(job_to_save)
            logger.info(f"Job {job_id}: Saved failed job to history")
        except Exception as save_error:
            logger.error(f"Failed to save failed job {job_id} to history: {save_error}")
            
    finally:
        # Clean up the temporary file
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Job {job_id}: Cleaned up temporary file: {file_path.name}")
        # Log total job duration
        import time as _t
        duration_s = _t.monotonic() - job_start
        with jobs_lock:
            status = jobs.get(job_id, {}).get('status', 'UNKNOWN')
            filename = jobs.get(job_id, {}).get('filename', file_path.name)
        logger.info(f"Job {job_id} finished with status {status} in {duration_s:.2f}s (file: {filename})")


@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(e):
    max_size_gb = app.config['MAX_CONTENT_LENGTH'] / (1024*1024*1024)
    return jsonify({
        'error': f"File too large! Maximum allowed size is {max_size_gb:.0f} GB. Please choose a smaller file."
    }), 413

@app.route('/')
def index():
    return render_template('index.html', active_page='upload')

@app.route('/history')
def history():
    """Display the history of all completed jobs."""
    return render_template('history.html', active_page='history')

@app.route('/api/history')
def get_history():
    """API endpoint to get all job history."""
    try:
        all_jobs = database.load_all_jobs()
        # Convert to list and sort by most recent first (assuming job IDs are timestamps)
        history_list = list(all_jobs.values())
        # Sort by status completion - completed first, then by ID (most recent first)
        history_list.sort(key=lambda x: (x.get('status') != 'COMPLETED', x.get('id')), reverse=True)
        return jsonify({'jobs': history_list})
    except Exception as e:
        logger.error(f"Failed to load history: {e}")
        return jsonify({'error': 'Failed to load history'}), 500

@app.route('/settings')
def settings_page():
    """Display the settings page."""
    return render_template('settings.html', active_page='settings')

@app.route('/api/settings', methods=['GET'])
def get_settings():
    """API endpoint to get current settings."""
    try:
        current_settings = settings.load_settings()
        # Don't send the actual API key for security, just indicate if it's set
        safe_settings = current_settings.copy()
        safe_settings['api_key'] = bool(current_settings.get('api_key'))
        return jsonify(safe_settings)
    except Exception as e:
        logger.error(f"Failed to load settings: {e}")
        return jsonify({'error': 'Failed to load settings'}), 500

@app.route('/api/settings', methods=['POST'])
def update_settings():
    """API endpoint to update settings."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        current_settings = settings.load_settings()
        
        # Update each provided setting
        for key, value in data.items():
            if key in ['model', 'api_key', 'summary_prompt', 'transcription_prompt', 'max_duration_seconds']:
                current_settings[key] = value
                logger.info(f"Updated setting: {key}")
        
        settings.save_settings(current_settings)
        return jsonify({'success': True, 'message': 'Settings updated successfully'})
        
    except Exception as e:
        logger.error(f"Failed to update settings: {e}")
        return jsonify({'error': 'Failed to update settings'}), 500

@app.route('/summarize', methods=['POST'])
def summarize_route():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '' or file.filename is None:
        return jsonify({'error': 'No selected file'}), 400

    # Create a unique job ID first to include it in the saved filename (avoid collisions)
    job_id = str(uuid.uuid4())

    # Build a unique filename: <job_id>_<original_name>
    original_name = secure_filename(file.filename)
    unique_filename = f"{job_id}_{original_name}" if original_name else job_id
    save_path = Path(app.config['UPLOAD_FOLDER']) / unique_filename
    file.save(save_path)
    
    # Create job data with proper timestamp
    from datetime import datetime
    job_data = {
        'id': job_id,
        'status': 'PENDING', 
        'progress': 0,
        'status_message': 'Initializing...',
        'summary': None, 
        'transcript': None, 
        'error': None,
    'filename': unique_filename,
        'created_at': datetime.now().isoformat(),
        'completed_at': None
    }
    
    with jobs_lock:
        jobs[job_id] = job_data.copy()
    
    # Save to history immediately so it shows up in history page
    try:
        database.save_job(job_data)
        logger.info(f"Job {job_id}: Added to history with PENDING status")
    except Exception as e:
        logger.error(f"Failed to save job {job_id} to history: {e}")

    # Submit the task to run in the background
    executor.submit(run_summarization_task, job_id, str(save_path))

    return jsonify({'job_id': job_id})

@app.route('/health', methods=['GET'])
def health():
    """Basic health endpoint for liveness checks."""
    try:
        with jobs_lock:
            job_count = len(jobs)
        return jsonify({'status': 'ok', 'jobs_in_memory': job_count}), 200
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({'status': 'error'}), 500

@app.route('/status/<job_id>')
def get_status(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return jsonify({'status': 'NOT_FOUND'}), 404
        # Return a copy of the job dictionary
        return jsonify(job)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)