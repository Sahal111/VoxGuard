FROM python:3.12-slim

WORKDIR /app

# Install shared contracts
COPY packages/contracts /tmp/contracts
RUN pip install --no-cache-dir /tmp/contracts && rm -rf /tmp/contracts

# Install service
COPY services/voter-service/pyproject.toml .
RUN pip install --no-cache-dir .

COPY services/voter-service/app app/

EXPOSE 8002

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
