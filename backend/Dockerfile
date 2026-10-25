FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 TANDEM_DATA_DIR=/data

RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY tandem tandem
COPY catalog catalog
CMD uvicorn tandem.api:app --host 0.0.0.0 --port ${PORT:-8000}
