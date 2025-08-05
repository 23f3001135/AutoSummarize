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

Path(app.config['UPLOAD_FOLDER']).mkdir(parents=True, exist_ok=True)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def run_summarization_task(job_id, file_path_str):
    """The function that will run in a background thread."""
    file_path = Path(file_path_str)
    logger.info(f"Job {job_id}: Starting processing for {file_path.name}")
    
    try:
        # Set status to PROCESSING
        with jobs_lock:
            jobs[job_id]['status'] = 'PROCESSING'

        # This is the long-running call to the Gemini API
        result_data = process_single_file(file_path) # This now returns a dictionary

        if not result_data or not result_data.get('summary'):
            raise ValueError("Processing returned no summary.")

        # Store the successful result
        with jobs_lock:
            jobs[job_id]['status'] = 'COMPLETED'
            jobs[job_id]['summary'] = result_data['summary']
            jobs[job_id]['transcript'] = result_data.get('transcript')
            # Add the job ID to the job data for saving
            job_to_save = jobs[job_id].copy()
            job_to_save['id'] = job_id
        
        database.save_job(job_to_save)
        logger.info(f"Job {job_id}: Successfully generated and saved summary and transcript.")

    except Exception as e:
        # Store the failure result
        logger.error(f"Job {job_id}: An error occurred: {e}", exc_info=True)
        with jobs_lock:
            jobs[job_id]['status'] = 'FAILURE'
            jobs[job_id]['error'] = str(e)
    finally:
        # Clean up the temporary file
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Job {job_id}: Cleaned up temporary file: {file_path.name}")


@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(e):
    return jsonify({'error': f"File is too large. Max size is {app.config['MAX_CONTENT_LENGTH'] / (1024*1024):.0f} MB."}), 413

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/history')
def history():
    """Display the history of all completed jobs."""
    return render_template('history.html')

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

@app.route('/summarize', methods=['POST'])
def summarize_route():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    filename = secure_filename(file.filename)
    save_path = Path(app.config['UPLOAD_FOLDER']) / filename
    file.save(save_path)
    
    # Create a unique job ID and store its initial state
    job_id = str(uuid.uuid4())
    with jobs_lock:
        jobs[job_id] = {'status': 'PENDING', 'summary': None, 'transcript': None, 'error': None}

    # Submit the task to run in the background
    executor.submit(run_summarization_task, job_id, str(save_path))

    return jsonify({'job_id': job_id})

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
