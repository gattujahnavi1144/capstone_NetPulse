# NetPulse API

A small FastAPI modular monolith with in-memory device storage. Device routes delegate to a service, which uses the repository and publishes domain events.

Install dependencies and start the development server from the project root:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`; interactive documentation is at `/docs`. Device data resets when the process restarts.