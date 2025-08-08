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
import settings
from models import db, Job

# --- In-Memory State ---
# A thread-safe dictionary to store live job status and results (for fast polling)
jobs = {}
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

# Database (SQLite via Flask-SQLAlchemy)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///autosummarize.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

with app.app_context():
    db.create_all()

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
    # Persist occasional progress updates (best-effort)
    try:
        from flask import has_app_context
        if has_app_context():
            job = Job.query.get(job_id)
            if job:
                job.progress = int(progress or 0)
                job.status_message = message
                db.session.commit()
    except Exception as _e:
        logger.debug(f"Non-fatal: couldn't persist progress for {job_id}: {_e}")

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
        # Persist transition to DB
        try:
            with app.app_context():
                job_row = Job.query.get(job_id)
                if job_row:
                    job_row.status = 'PROCESSING'
                    job_row.progress = 0
                    job_row.status_message = 'Starting upload...'
                    db.session.commit()
        except Exception as _e:
            logger.debug(f"Couldn't persist PROCESSING state for {job_id}: {_e}")

        # Update progress through different stages
        update_job_progress(job_id, 5, '📤 Uploading file...')
        
        # This is the long-running call to the Gemini API
        result_data = process_single_file(file_path, lambda p, m: update_job_progress(job_id, p, m))

        # Treat explicit errors as failures and ensure summary exists
        if (not result_data) or result_data.get('error') or (not result_data.get('summary')):
            raise ValueError(result_data.get('error') or "Processing returned no summary.")

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
        # Persist to DB
        try:
            with app.app_context():
                job_row = Job.query.get(job_id)
                if job_row:
                    job_row.status = 'COMPLETED'
                    job_row.summary = job_to_save.get('summary')
                    job_row.transcript = job_to_save.get('transcript')
                    job_row.progress = 100
                    job_row.completed_at = datetime.fromisoformat(job_to_save['completed_at'])
                    job_row.status_message = 'Completed'
                    db.session.commit()
        except Exception as _e:
            logger.error(f"Failed to persist completed job {job_id}: {_e}")
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
        # Persist failure to DB
        try:
            with app.app_context():
                job_row = Job.query.get(job_id)
                if job_row:
                    job_row.status = 'FAILED'
                    job_row.error = job_to_save.get('error')
                    from datetime import datetime as _dt
                    job_row.completed_at = _dt.fromisoformat(job_to_save['completed_at'])
                    job_row.status_message = 'Failed'
                    db.session.commit()
            logger.info(f"Job {job_id}: Saved failed job to history (DB)")
        except Exception as save_error:
            logger.error(f"Failed to save failed job {job_id} to DB: {save_error}")
            
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

@app.route('/api/history/<job_id>', methods=['DELETE'])
def delete_history_item(job_id):
    """Delete a job from history DB."""
    try:
        with app.app_context():
            job = Job.query.get(job_id)
            if not job:
                return jsonify({'error': 'Not found'}), 404
            db.session.delete(job)
            db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Failed to delete job {job_id}: {e}")
        return jsonify({'error': 'Failed to delete'}), 500

@app.route('/api/history')
def get_history():
    """API endpoint to get all job history from the database."""
    try:
        with app.app_context():
            # Order by: completed_at present last=False (i.e., completed first), then completed_at desc, then created_at desc
            jobs_q = Job.query.order_by((Job.completed_at.is_(None)).asc(), Job.completed_at.desc(), Job.created_at.desc()).all()
            history_list = [j.to_dict() for j in jobs_q]
        return jsonify({'jobs': history_list})
    except Exception as e:
        logger.error(f"Failed to load history: {e}")
        return jsonify({'error': 'Failed to load history'}), 500

@app.route('/settings')
def settings_page():
    """Display the settings page."""
    return render_template('settings.html', active_page='settings')

@app.route('/api/has_api_key', methods=['GET'])
def has_api_key():
    """Return whether the Gemini API key is configured."""
    try:
        current_settings = settings.load_settings()
        is_set = bool(os.getenv('GEMINI_API_KEY') or current_settings.get('api_key'))
        return jsonify({ 'hasApiKey': is_set })
    except Exception as e:
        logger.error(f"Failed to check API key: {e}")
        return jsonify({ 'hasApiKey': False })

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
        
        # Delegate to settings module (which uses DB if available)
        current_settings = settings.load_settings()
        for key, value in data.items():
            if key in ['model', 'api_key', 'summary_prompt', 'transcription_prompt', 'max_duration_seconds']:
                current_settings[key] = value
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

    # Persist to DB so it shows up in history immediately
    try:
        with app.app_context():
            job_row = Job()
            job_row.id = job_data['id']
            job_row.filename = job_data['filename']
            job_row.status = job_data['status']
            job_row.progress = job_data['progress']
            job_row.status_message = job_data['status_message']
            from datetime import datetime as _dt
            job_row.created_at = _dt.fromisoformat(job_data['created_at'])
            db.session.add(job_row)
            db.session.commit()
            logger.info(f"Job {job_id}: Added to DB with PENDING status")
    except Exception as e:
        logger.error(f"Failed to persist job {job_id} to DB: {e}")

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