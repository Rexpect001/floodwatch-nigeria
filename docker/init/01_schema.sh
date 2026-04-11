#!/bin/bash
# Docker entrypoint init script — runs once on first DB container boot.
# Applies all schema files in order, then seeds reference data.
# PostgreSQL runs scripts in /docker-entrypoint-initdb.d/ alphabetically.

set -e

DB="climate_ews"
USER="climate_user"

echo "[init] Applying schema.sql..."
psql -v ON_ERROR_STOP=1 --username "$USER" --dbname "$DB" \
  -f /docker-entrypoint-initdb.d/schema.sql

echo "[init] Applying schema_voice.sql..."
psql -v ON_ERROR_STOP=1 --username "$USER" --dbname "$DB" \
  -f /docker-entrypoint-initdb.d/schema_voice.sql

echo "[init] Applying schema_missing_tables.sql..."
psql -v ON_ERROR_STOP=1 --username "$USER" --dbname "$DB" \
  -f /docker-entrypoint-initdb.d/schema_missing_tables.sql

echo "[init] Applying seed.sql..."
psql -v ON_ERROR_STOP=1 --username "$USER" --dbname "$DB" \
  -f /docker-entrypoint-initdb.d/seed.sql

echo "[init] Database initialised successfully."
