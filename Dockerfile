# The API only. The Streamlit app is not built into this image and is not
# affected by it.
FROM python:3.11-slim

WORKDIR /app

# Dependencies first, so a code change does not re-download torch.
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

# The engine, its data, and the page it serves. venv/, audio/, results/ and
# scripts/ are excluded by .dockerignore — the first is host-specific and the
# rest are development tooling.
COPY data/ ./data/
COPY logic/ ./logic/
COPY web/ ./web/
COPY api.py .

COPY prefetch_model.py .
RUN python prefetch_model.py

ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn api:app --host 0.0.0.0 --port ${PORT:-8000}"]
