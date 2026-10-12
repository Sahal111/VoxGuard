FROM python:3.12-slim

WORKDIR /app

# Install shared contracts
COPY packages/contracts /tmp/contracts
RUN pip install --no-cache-dir /tmp/contracts && rm -rf /tmp/contracts

# Install service
COPY services/audit-service/pyproject.toml .
RUN pip install --no-cache-dir .

COPY services/audit-service/app app/
COPY services/audit-service/alembic.ini alembic.ini
COPY services/audit-service/alembic alembic/

EXPOSE 8004

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8004"]
