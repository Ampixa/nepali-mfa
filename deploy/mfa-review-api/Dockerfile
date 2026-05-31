FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir flask gunicorn

COPY app.py /app/app.py

ENV PORT=8003
EXPOSE 8003

CMD ["sh", "-c", "gunicorn -w 2 -b 0.0.0.0:${PORT} app:app"]
