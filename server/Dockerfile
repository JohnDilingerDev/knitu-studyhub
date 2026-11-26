FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home --uid 10001 studyhub
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini .
COPY seed ./seed
USER studyhub
EXPOSE 8000
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
