# AutoSummarize

Enterprise‑style meeting and media summarization service. Upload an audio or video file (up to 5 GB), the system normalizes it to MP3, transcribes it using Google Gemini, and produces a structured executive summary plus a full transcript. Includes persistent job history (SQLite), modern Tailwind UI, API key management, and resilient background processing.

## Key Features
- Large File Support: Handles uploads up to 5 GB with background processing and progress polling.
- Automatic Normalization: All media converted to a consistent MP3 profile (FFmpeg) for reliable transcription.
- Short vs Long Workflow: Direct processing for short files; chunked, sequential transcription for long ones.
- Structured Executive Summaries: Corporate‑ready minutes with objectives, key points, decisions, action items.
- Full Transcript Generation: Verbatim transcription (prompt-driven) stored alongside the summary.
- Persistent History: Job metadata, status, timestamps, summary, and transcript stored in SQLite via SQLAlchemy.
- Live Status & Progress: Fine‑grained progress states surfaced to the UI with adaptive messaging.
- Resilient Error Handling: Failed jobs retained with error context; UI displays status clearly.
- Markdown Rendering: Rich formatting of summaries & transcripts using Marked.js (sanitized display areas).
- API Key Management: DB‑backed settings with first‑load modal prompt if no Google Gemini API key is set.
- Delete History Items: Remove individual jobs via REST endpoint + UI action.
- Dark / Light Mode: Persistent theme preference with modern “glass” UI touches.
- Health Endpoint: /health returns simple JSON for liveness checks.

## Architecture Overview
| Layer | Responsibility |
|-------|----------------|
| Flask App (`app.py`) | Routing, job submission, status polling, settings & history APIs. |
| Processing (`processing/media_handler.py`) | Normalization, duration detection, splitting, orchestration of Gemini calls. |
| Gemini Client (`processing/gemini_processor.py`) | Transcription + summary generation with retries & exponential backoff. |
| Persistence (`models.py`) | SQLAlchemy models: `Job`, `Setting`. |
| Settings (`settings.py`) | DB-backed config (model, prompts, max duration, API key). |
| Templates (`templates/`) | Tailwind‑based UI: upload, history, settings, modals. |
| Background Execution | `ThreadPoolExecutor` (2 workers) + in‑memory job map for fast polling. |

### Job Lifecycle
1. Client uploads file → `/summarize` returns a `job_id` immediately.
2. File saved under `temporary_uploads/<job_id>_originalName`.
3. Background thread normalizes media to MP3, probes duration.
4. If duration <= threshold: single transcription → summary.
5. Else: file is split into MP3 chunks; each chunk transcribed sequentially with pacing.
6. Final transcript aggregated → summary generated → DB updated → UI reports completion.
7. Temporary upload removed after processing.

### Normalization Strategy
All inputs (audio or video) are converted to a standardized MP3 (`libmp3lame`, 160k, 44.1 kHz, stereo). This eliminates edge cases from uncommon containers/codecs (e.g., `.m4a`, `.mov`, variable codec packaging) and ensures consistent downstream behavior.

## Tech Stack
- Python 3.13 (free‑threaded build in Docker image)
- Flask + Flask‑SQLAlchemy
- SQLite (file: `autosummarize.db`)
- Google Gemini (via `google-genai`)
- FFmpeg / FFprobe
- Tailwind CSS (CDN)
- Gunicorn (deployment entrypoint)

## API Endpoints (Selected)
- `POST /summarize` – Upload media, start job → `{ job_id }`
- `GET /status/<job_id>` – Live status & progress
- `GET /api/history` – List all jobs (most recent first)
- `DELETE /api/history/<job_id>` – Delete a job
- `GET /api/settings` / `POST /api/settings` – Retrieve/update settings (API key, prompts, etc.)
- `GET /api/has_api_key` – Boolean flag for first‑load modal
- `GET /health` – Liveness probe

## Data Model (Simplified)
`Job`: id, filename, status (PENDING/PROCESSING/COMPLETED/FAILED), progress, status_message, summary, transcript, error, created_at, completed_at.
`Setting`: key, value (JSON‑serialized strings).

## Running Locally (Without Docker)
```bash
# (Optionally) create a virtual environment
python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

# Set API key (or enter via UI modal later)
export GEMINI_API_KEY=your_key_here

python app.py  # Runs on http://localhost:8080
```

## Docker Usage
```bash
# Build
docker build -t autosummarize .

# Run (expose port 8080)
docker run --rm -p 8080:8080 \
  -e GEMINI_API_KEY=your_key_here \
  -v $(pwd)/temporary_uploads:/app/temporary_uploads \
  autosummarize
```

## Configuration & Settings
Values stored in the `settings` table (editable via UI or POST /api/settings):
| Key | Description | Example |
|-----|-------------|---------|
| api_key | Google Gemini API key (masked in UI) | `sk-...` |
| model | Gemini model for transcription & summary | `gemini-2.5-flash` |
| summary_prompt | Prompt template for summary generation | (Markdown text) |
| transcription_prompt | Prompt for verbatim transcription | (Plain text) |
| max_duration_seconds | Threshold for splitting | `3600` |

Environment variable `GEMINI_API_KEY` overrides stored key for process lifetime.

## Progress Semantics
| Phase | Approx % | Description |
|-------|----------|-------------|
| Upload/Validation | 0–20 | File saved, normalized, probed |
| Dispatch / API Calls | 20–80 | Transcription (single or chunks) |
| Summary Generation | 80–95 | Aggregating + summarizing |
| Finalization | 95–100 | Persist & response ready |

## Error Handling
- Any exception during transcription or summarization → job marked FAILED with `error` message.
- History preserves failed entries for auditability.
- RequestEntityTooLarge handled with friendly JSON (max 5 GB).

## Security & Privacy
- API key stored locally in SQLite (not exposed in plain text via API; UI masks it).
- Uploaded media removed after processing completes.
- No external persistence beyond SQLite DB unless you mount volumes.

## Scaling Considerations / Future Enhancements
| Area | Next Step |
|------|-----------|
| Concurrency | Move from ThreadPool to Celery/Redis for distributed workers. |
| Storage | Offload originals & normalized audio to S3/GCS. |
| Streaming | Implement chunked streaming upload & progressive transcription. |
| Auth | Add user accounts / API tokens if multi-tenant. |
| Formats | Add remux-first path to avoid re-encode when codecs already compatible. |
| Observability | Structured logs + metrics (Prometheus / OpenTelemetry). |

## Development Tips
- Tailwind via CDN → rapid iteration; if customizing heavily, integrate a build step later.
- Use `sqlite3 autosummarize.db '.tables'` to inspect tables.
- For large test files, generate synthetic audio: `ffmpeg -f lavfi -i sine=frequency=1000:duration=4000 test_long.wav`.

## Troubleshooting
| Symptom | Cause | Resolution |
|---------|-------|-----------|
| 413 on upload | File > 5 GB | Trim or compress source media |
| Job stuck PROCESSING | External API latency / transient error | Check logs; retries handled internally |
| Empty summary | Transcription failed silently | See job error message; verify audio integrity |
| API key modal keeps showing | Key not saved (DB issue) | Inspect logs; ensure write permissions |

## License
Proprietary / Internal (adjust this section as needed).

## Disclaimer
This project uses Google Gemini APIs; ensure usage complies with applicable terms and data policies.

---
Maintained by the internal team. Contributions: open a PR with a concise description and test evidence.
