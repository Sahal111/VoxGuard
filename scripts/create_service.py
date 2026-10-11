"""
Service skeleton generation helper.
Run: python3 scripts/create_service.py <service-name> <port> [--with-db <db_name>]
"""

import argparse
import os
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVICES_DIR = ROOT / "services"


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        print(f"  SKIP (exists): {path.relative_to(ROOT)}")
        return
    path.write_text(textwrap.dedent(content).lstrip())
    print(f"  CREATE: {path.relative_to(ROOT)}")


def create_service(name: str, port: int, db_name: str | None = None) -> None:
    svc = SERVICES_DIR / name
    slug = name.replace("-", "_")
    db_env_var = f"{slug.upper().replace('_SERVICE', '')}_DATABASE_URL"
    db_env_var_sync = f"{db_env_var}_SYNC"

    # --- pyproject.toml ---
    db_deps = ""
    if db_name:
        db_deps = """
    "sqlalchemy[asyncio]>=2.0,<3",
    "asyncpg>=0.29,<1",
    "alembic>=1.13,<2",
    "psycopg2-binary>=2.9,<3","""

    write(svc / "pyproject.toml", f"""\
        [build-system]
        requires = ["hatchling"]
        build-backend = "hatchling.build"

        [project]
        name = "voxguard-{name}"
        version = "0.1.0"
        description = "VoxGuard {name}"
        requires-python = ">=3.10"
        dependencies = [
            "fastapi>=0.115,<1",
            "uvicorn[standard]>=0.32,<1",
            "pydantic-settings>=2.6,<3",
            "httpx>=0.27,<1",{db_deps}
        ]

        [project.optional-dependencies]
        dev = [
            "pytest>=8.0,<9",
            "pytest-asyncio>=0.24,<1",
            "httpx>=0.27,<1",
        ]
    """)

    # --- Dockerfile ---
    write(svc / "Dockerfile", f"""\
        FROM python:3.12-slim

        WORKDIR /app

        # Install shared contracts
        COPY packages/contracts /tmp/contracts
        RUN pip install --no-cache-dir /tmp/contracts && rm -rf /tmp/contracts

        # Install service
        COPY services/{name}/pyproject.toml .
        RUN pip install --no-cache-dir .

        COPY services/{name}/app app/

        EXPOSE {port}

        CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "{port}"]
    """)

    # --- app/main.py ---
    db_imports = ""
    db_ready_check = ""
    db_lifespan = ""
    if db_name:
        db_imports = "from app.infrastructure.database import check_db_ready"
        db_ready_check = f'''
    db_ok, db_msg = await check_db_ready()
    if not db_ok:
        checks["database"] = {{"status": "unavailable", "error": db_msg}}
        all_ok = False
    else:
        checks["database"] = {{"status": "ok"}}'''

    write(svc / "app" / "main.py", f'''\
        """VoxGuard {name} — FastAPI application."""

        from __future__ import annotations

        import logging
        import time
        import uuid
        from contextlib import asynccontextmanager

        from fastapi import FastAPI, Request, Response
        from fastapi.responses import JSONResponse

        from app.core.config import settings
        {db_imports}

        logger = logging.getLogger("{slug}")


        @asynccontextmanager
        async def lifespan(app: FastAPI):
            """Startup / shutdown."""
            logger.info("{name} starting", extra={{"service": "{name}", "port": {port}}})
            yield
            logger.info("{name} shutting down")


        app = FastAPI(
            title="VoxGuard {name}",
            version="0.1.0",
            docs_url="/docs" if settings.APP_ENV in ("local", "test") else None,
            lifespan=lifespan,
        )


        # ── Middleware: Request ID & Correlation ID ──────────────────────
        @app.middleware("http")
        async def request_context(request: Request, call_next):
            request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
            correlation_id = request.headers.get("x-correlation-id") or request_id
            request.state.request_id = request_id
            request.state.correlation_id = correlation_id

            start = time.monotonic()
            response: Response = await call_next(request)
            elapsed_ms = round((time.monotonic() - start) * 1000, 2)

            response.headers["X-Request-ID"] = request_id
            response.headers["X-Correlation-ID"] = correlation_id

            logger.info(
                "request",
                extra={{
                    "service": "{name}",
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "elapsed_ms": elapsed_ms,
                    "request_id": request_id,
                    "correlation_id": correlation_id,
                }},
            )
            return response


        # ── Error handler ───────────────────────────────────────────────
        @app.exception_handler(Exception)
        async def global_exception_handler(request: Request, exc: Exception):
            request_id = getattr(request.state, "request_id", "unknown")
            logger.exception(
                "unhandled_error",
                extra={{"service": "{name}", "request_id": request_id}},
            )
            return JSONResponse(
                status_code=500,
                content={{
                    "error": {{
                        "code": "INTERNAL_ERROR",
                        "message": "An unexpected error occurred.",
                        "details": [],
                        "request_id": request_id,
                    }}
                }},
            )


        # ── Health endpoints ────────────────────────────────────────────
        @app.get("/health/live", tags=["health"])
        async def health_live():
            return {{"status": "ok", "service": "{name}"}}


        @app.get("/health/ready", tags=["health"])
        async def health_ready():
            checks = {{}}
            all_ok = True
            {db_ready_check}
            status = "ok" if all_ok else "degraded"
            code = 200 if all_ok else 503
            return JSONResponse(
                status_code=code,
                content={{"status": status, "service": "{name}", "checks": checks}},
            )
    ''')

    # --- app/core/__init__.py ---
    write(svc / "app" / "core" / "__init__.py", "")

    # --- app/core/config.py ---
    db_field = ""
    if db_name:
        db_field = f"""
    {db_env_var}: str
    {db_env_var_sync}: str = ""
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 5
    DB_POOL_TIMEOUT: int = 10"""

    write(svc / "app" / "core" / "config.py", f'''\
        """Configuration loaded from environment variables."""

        from pydantic_settings import BaseSettings


        class Settings(BaseSettings):
            APP_ENV: str = "local"
            {db_field}

            model_config = {{"env_file": ".env", "extra": "ignore"}}


        settings = Settings()
    ''')

    # --- app/api/__init__.py ---
    write(svc / "app" / "api" / "__init__.py", "")

    # --- app/schemas/__init__.py ---
    write(svc / "app" / "schemas" / "__init__.py", "")

    # --- app/services/__init__.py ---
    write(svc / "app" / "services" / "__init__.py", "")

    # --- app/__init__.py ---
    write(svc / "app" / "__init__.py", "")

    # --- Database infrastructure ---
    if db_name:
        write(svc / "app" / "infrastructure" / "__init__.py", "")

        write(svc / "app" / "infrastructure" / "database.py", f'''\
            """Database engine and session management for {name}."""

            from __future__ import annotations

            import logging
            from collections.abc import AsyncGenerator

            from sqlalchemy.ext.asyncio import (
                AsyncSession,
                async_sessionmaker,
                create_async_engine,
            )
            from sqlalchemy import text

            from app.core.config import settings

            logger = logging.getLogger("{slug}.db")

            engine = create_async_engine(
                settings.{db_env_var},
                pool_size=settings.DB_POOL_SIZE,
                max_overflow=settings.DB_MAX_OVERFLOW,
                pool_timeout=settings.DB_POOL_TIMEOUT,
                pool_pre_ping=True,
            )

            async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


            async def get_session() -> AsyncGenerator[AsyncSession, None]:
                async with async_session() as session:
                    yield session


            async def check_db_ready(timeout: float = 3.0) -> tuple[bool, str]:
                """Check database connectivity with timeout."""
                try:
                    async with engine.connect() as conn:
                        await conn.execute(text("SELECT 1"))
                    return True, "ok"
                except Exception as exc:
                    logger.warning("db_health_check_failed", extra={{"error": str(exc)[:200]}})
                    return False, str(exc)[:200]
        ''')

        # --- Alembic config ---
        write(svc / "alembic.ini", f'''\
            [alembic]
            script_location = alembic
            sqlalchemy.url = %(DATABASE_URL)s

            [loggers]
            keys = root,sqlalchemy,alembic

            [handlers]
            keys = console

            [formatters]
            keys = generic

            [logger_root]
            level = WARN
            handlers = console

            [logger_sqlalchemy]
            level = WARN
            handlers =
            qualname = sqlalchemy.engine

            [logger_alembic]
            level = INFO
            handlers =
            qualname = alembic

            [handler_console]
            class = StreamHandler
            args = (sys.stderr,)
            level = NOTSET
            formatter = generic

            [formatter_generic]
            format = %(levelname)-5.5s [%(name)s] %(message)s
        ''')

        write(svc / "alembic" / "env.py", f'''\
            """Alembic environment for {name}."""

            import os
            from logging.config import fileConfig

            from alembic import context
            from sqlalchemy import engine_from_config, pool

            config = context.config

            if config.config_file_name is not None:
                fileConfig(config.config_file_name)

            # Override URL from environment
            db_url = os.environ.get("{db_env_var_sync}", "")
            if db_url:
                config.set_main_option("sqlalchemy.url", db_url)

            target_metadata = None


            def run_migrations_offline() -> None:
                url = config.get_main_option("sqlalchemy.url")
                context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
                with context.begin_transaction():
                    context.run_migrations()


            def run_migrations_online() -> None:
                connectable = engine_from_config(
                    config.get_section(config.config_ini_section, {{}}),
                    prefix="sqlalchemy.",
                    poolclass=pool.NullPool,
                )
                with connectable.connect() as connection:
                    context.configure(connection=connection, target_metadata=target_metadata)
                    with context.begin_transaction():
                        context.run_migrations()


            if context.is_offline_mode():
                run_migrations_offline()
            else:
                run_migrations_online()
        ''')

        write(svc / "alembic" / "versions" / ".gitkeep", "")

        write(svc / "alembic" / "script.py.mako", '''\
            """${message}

            Revision ID: ${up_revision}
            Revises: ${down_revision | comma,n}
            Create Date: ${create_date}
            """

            from typing import Sequence, Union

            from alembic import op
            import sqlalchemy as sa

            revision: str = ${repr(up_revision)}
            down_revision: Union[str, None] = ${repr(down_revision)}
            branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
            depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


            def upgrade() -> None:
                ${upgrades if upgrades else "pass"}


            def downgrade() -> None:
                ${downgrades if downgrades else "pass"}
        ''')

    # --- Tests ---
    write(svc / "tests" / "__init__.py", "")

    write(svc / "tests" / "test_health.py", f'''\
        """Tests for {name} health endpoints."""

        import pytest
        from httpx import ASGITransport, AsyncClient

        from app.main import app


        @pytest.fixture
        async def client():
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                yield ac


        @pytest.mark.asyncio
        async def test_health_live(client):
            resp = await client.get("/health/live")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert data["service"] == "{name}"


        @pytest.mark.asyncio
        async def test_health_live_returns_request_id(client):
            resp = await client.get("/health/live", headers={{"X-Request-ID": "test-req-123"}})
            assert resp.headers.get("x-request-id") == "test-req-123"


        @pytest.mark.asyncio
        async def test_health_ready(client):
            resp = await client.get("/health/ready")
            # Without real DB, may return 503 or 200 depending on service
            assert resp.status_code in (200, 503)
            data = resp.json()
            assert "status" in data
            assert data["service"] == "{name}"
    ''')

    write(svc / "tests" / "conftest.py", f'''\
        """Pytest configuration for {name}."""

        import os
        os.environ.setdefault("APP_ENV", "test")
    ''')

    print(f"✓ Service '{name}' created at services/{name}/")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    parser.add_argument("port", type=int)
    parser.add_argument("--with-db", dest="db_name", default=None)
    args = parser.parse_args()
    create_service(args.name, args.port, args.db_name)


if __name__ == "__main__":
    main()
