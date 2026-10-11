FROM python:3.12-slim

WORKDIR /app

# Install shared contracts
COPY packages/contracts /tmp/contracts
RUN pip install --no-cache-dir /tmp/contracts && rm -rf /tmp/contracts

# Install service
COPY services/api-gateway/pyproject.toml .
RUN pip install --no-cache-dir .

COPY services/api-gateway/app app/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
