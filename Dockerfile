FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY datasets ./datasets
COPY dashboards ./dashboards
COPY status/dataset_freshness.example.yaml ./status/dataset_freshness.example.yaml

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir .

EXPOSE 8001

CMD ["python", "-m", "src.server", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8001"]
