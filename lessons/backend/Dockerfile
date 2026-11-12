FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-nanum \
    && rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml ./backend/pyproject.toml
COPY backend/app ./backend/app
RUN python -m pip install --no-cache-dir -e "./backend[google-cloud,gemini]"

COPY lessons/backend/pyproject.toml ./lessons/backend/pyproject.toml
COPY lessons/backend/lessons_app ./lessons/backend/lessons_app
RUN python -m pip install --no-cache-dir -e "./lessons/backend"

COPY lessons/frontend ./lessons/frontend

WORKDIR /app/lessons/backend
EXPOSE 8080
CMD ["uvicorn", "lessons_app.main:app", "--host", "0.0.0.0", "--port", "8080"]
