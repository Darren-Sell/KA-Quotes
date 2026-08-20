FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY static ./static
COPY server.py .

# The SQLite database lives here — mount a persistent volume at this path
# on your host so data survives restarts and redeploys.
ENV DATABASE_PATH=/data/app.db
RUN mkdir -p /data

EXPOSE 8080
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "4", "--timeout", "60", "server:app"]
