#!/bin/bash
# ============================================================
# VoxGuard — PostgreSQL initialization script
# Creates per-service databases and roles.
# Runs only on first container start (when volume is empty).
# ============================================================

set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<-EOSQL

    -- ── Roles (one per service) ────────────────────────────────
    CREATE ROLE auth_app     WITH LOGIN PASSWORD '${AUTH_DB_PASSWORD:-changeme_auth}';
    CREATE ROLE voter_app    WITH LOGIN PASSWORD '${VOTER_DB_PASSWORD:-changeme_voter}';
    CREATE ROLE ballot_app   WITH LOGIN PASSWORD '${BALLOT_DB_PASSWORD:-changeme_ballot}';
    CREATE ROLE audit_app    WITH LOGIN PASSWORD '${AUDIT_DB_PASSWORD:-changeme_audit}';
    CREATE ROLE result_app   WITH LOGIN PASSWORD '${RESULT_DB_PASSWORD:-changeme_result}';
    CREATE ROLE security_app WITH LOGIN PASSWORD '${SECURITY_DB_PASSWORD:-changeme_security}';

    -- ── Databases ──────────────────────────────────────────────
    CREATE DATABASE auth_db     OWNER auth_app;
    CREATE DATABASE voter_db    OWNER voter_app;
    CREATE DATABASE ballot_db   OWNER ballot_app;
    CREATE DATABASE audit_db    OWNER audit_app;
    CREATE DATABASE result_db   OWNER result_app;
    CREATE DATABASE security_db OWNER security_app;

    -- ── Grant connect ──────────────────────────────────────────
    GRANT CONNECT ON DATABASE auth_db     TO auth_app;
    GRANT CONNECT ON DATABASE voter_db    TO voter_app;
    GRANT CONNECT ON DATABASE ballot_db   TO ballot_app;
    GRANT CONNECT ON DATABASE audit_db    TO audit_app;
    GRANT CONNECT ON DATABASE result_db   TO result_app;
    GRANT CONNECT ON DATABASE security_db TO security_app;

    -- ── Revoke public access to prevent cross-service access ──
    REVOKE ALL ON DATABASE auth_db     FROM PUBLIC;
    REVOKE ALL ON DATABASE voter_db    FROM PUBLIC;
    REVOKE ALL ON DATABASE ballot_db   FROM PUBLIC;
    REVOKE ALL ON DATABASE audit_db    FROM PUBLIC;
    REVOKE ALL ON DATABASE result_db   FROM PUBLIC;
    REVOKE ALL ON DATABASE security_db FROM PUBLIC;

EOSQL

echo "✓ VoxGuard databases and roles initialized."
