FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-nanum \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY app ./app

ARG INSTALL_GOOGLE_CLOUD=true
RUN if [ "$INSTALL_GOOGLE_CLOUD" = "true" ]; then \
      python -m pip install --no-cache-dir -e ".[google-cloud,gemini]"; \
    else \
      python -m pip install --no-cache-dir -e .; \
    fi

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
