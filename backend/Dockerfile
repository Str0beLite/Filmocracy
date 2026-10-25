FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 TANDEM_DATA_DIR=/data HF_HOME=/app/.hf

RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Bake the tag encoder weights into the image so boot doesn't download them.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"

COPY app.py api_models.py recommendations.py session_recommendations.py unified.py ./
COPY tandem tandem
COPY catalog catalog
CMD ["sh", "-c", "exec uvicorn unified:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
