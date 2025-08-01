import os
from pathlib import Path
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge

# Import the celery task and the result object
from tasks import summarize_task
from celery.result import AsyncResult

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'temporary_uploads'
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024  # 1 Gigabyte

# Ensure the upload folder exists
Path(app.config['UPLOAD_FOLDER']).mkdir(parents=True, exist_ok=True)


@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(e):
    """Handles file uploads that exceed the size limit."""
    return jsonify({'error': f"File is too large. Max size is {app.config['MAX_CONTENT_LENGTH'] / (1024*1024):.0f} MB."}), 413

@app.route('/')
def index():
    """Renders the main page."""
    return render_template('index.html')

@app.route('/summarize', methods=['POST'])
def summarize_route():
    """
    Handles file upload and dispatches a background task.
    No database is used. The task ID from Celery is the job ID.
    """
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    filename = secure_filename(file.filename)
    save_path = Path(app.config['UPLOAD_FOLDER']) / filename
    file.save(save_path)

    # Dispatch the background task. The task's ID is our job identifier.
    task = summarize_task.delay(str(save_path))

    # Immediately return the task ID to the client
    return jsonify({'job_id': task.id})

@app.route('/status/<job_id>')
def get_status(job_id):
    """
    Endpoint for the frontend to poll for job status updates.
    It checks the status directly from the Celery backend (Redis).
    """
    task_result = AsyncResult(job_id)
    
    status = task_result.status
    summary = None
    error = None

    if status == 'SUCCESS':
        # Task completed successfully, result is available
        summary = task_result.result
    elif status == 'FAILURE':
        # Task failed, the result is the exception
        error = str(task_result.result)
    
    # For PENDING or other states, we just return the status.
    # The frontend will map this to a user-friendly message.
    return jsonify({
        'status': status,
        'summary': summary,
        'error': error
    })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
