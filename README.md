# NetPulse API

A small FastAPI modular monolith with SQLite device and alert storage. Device routes delegate to a service, which uses the repository and publishes domain events.

Install dependencies and start the development server from the project root:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`; interactive documentation is at `/docs`. Data persists in `netpulse.db` in the working directory.

## ASGI and WSGI

FastAPI defines the API and runs as an ASGI application. Uvicorn is an ASGI server that receives HTTP requests and passes them to FastAPI. ASGI supports asynchronous work and long-lived connections; WSGI is the older, synchronous interface commonly used by traditional Python web applications.