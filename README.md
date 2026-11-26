# NetPulse API

A small FastAPI modular monolith with SQLite device and alert storage. Device routes delegate to a service, which uses the repository and publishes domain events.

From the project root, create a virtual environment, install dependencies, and start the development server:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`; interactive documentation is at `/docs`. Data persists in `netpulse.db` in the working directory. Existing data is retained across restarts. On Windows, activate the environment with `.venv\Scripts\Activate.ps1` instead.

Run the tests with `python -m pytest -q`. The tests use temporary SQLite databases, not `netpulse.db`.

## Logging

Application events are JSON lines with fields such as `event`, `level`, `timestamp`, `request_id`, and, for device events, `device_id`. A `request_completed` event also records `method`, route `path`, `status_code`, and `duration_ms`. INFO covers normal workflow and request completion, WARNING covers handled device errors, and ERROR covers unexpected exceptions with a sanitized stack trace.

`request_id` correlates events from one HTTP request; `device_id` identifies a device across requests. The server accepts an `X-Request-ID` containing 1-64 ASCII letters, numbers, underscores, or hyphens; otherwise it generates one. The response returns the selected ID. Use a distinct request ID for each request when possible.

For example, after registering a device in `/docs`, send a status update from Bash:

```bash
curl -i -X PATCH http://127.0.0.1:8000/devices/RTR-401/status \
	-H 'Content-Type: application/json' \
	-H 'X-Request-ID: lab-trace-401' \
	-d '{"status":"offline"}'
```

For PowerShell:

```powershell
Invoke-WebRequest -Method Patch -Uri 'http://127.0.0.1:8000/devices/RTR-401/status' `
	-Headers @{ 'X-Request-ID' = 'lab-trace-401' } -ContentType 'application/json' `
	-Body '{"status":"offline"}'
```

Search the server console for the response's request ID to correlate `device_status_changed`, `offline_alert_created`, and `request_completed`. Only an online-to-offline transition creates an alert; repeating an offline update does not. Reusing the same request ID for multiple requests groups their events together.

Never log passwords, tokens, credentials, connection URLs, whole request bodies, or personal data. Sensitive top-level fields are redacted as a last-resort safety net, not a substitute for safe logging; nested sensitive structures are not redacted. Application logs exclude query strings, but avoid putting secrets in URL paths or queries: unmatched-path redaction is heuristic and Uvicorn access logs are separate.

## ASGI and WSGI

FastAPI defines the API and runs as an ASGI application. Uvicorn is an ASGI server that receives HTTP requests and passes them to FastAPI. ASGI supports asynchronous work and long-lived connections; WSGI is the older, synchronous interface commonly used by traditional Python web applications. NetPulse uses synchronous SQLAlchemy sessions: synchronous endpoints run in FastAPI's worker threads, while the async probe currently performs its device lookup synchronously and can briefly block the event loop. An async database driver and SQLAlchemy async sessions would be needed for fully asynchronous database access.