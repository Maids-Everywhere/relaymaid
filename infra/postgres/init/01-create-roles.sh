#!/bin/sh
set -eu

: "${RELAYMAID_DB_NAME:?RELAYMAID_DB_NAME is required}"
: "${RELAYMAID_MIGRATOR_USER:?RELAYMAID_MIGRATOR_USER is required}"
: "${RELAYMAID_MIGRATOR_PASSWORD:?RELAYMAID_MIGRATOR_PASSWORD is required}"
: "${RELAYMAID_APP_USER:?RELAYMAID_APP_USER is required}"
: "${RELAYMAID_APP_PASSWORD:?RELAYMAID_APP_PASSWORD is required}"

psql \
    --set ON_ERROR_STOP=1 \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    --set database_name="$RELAYMAID_DB_NAME" \
    --set migrator_user="$RELAYMAID_MIGRATOR_USER" \
    --set migrator_password="$RELAYMAID_MIGRATOR_PASSWORD" \
    --set app_user="$RELAYMAID_APP_USER" \
    --set app_password="$RELAYMAID_APP_PASSWORD" <<'SQL'
CREATE ROLE :"migrator_user"
    LOGIN
    PASSWORD :'migrator_password'
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOINHERIT
    NOBYPASSRLS;

CREATE ROLE :"app_user"
    LOGIN
    PASSWORD :'app_password'
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOINHERIT
    NOBYPASSRLS;

CREATE DATABASE :"database_name"
    OWNER :"migrator_user";

REVOKE ALL
    ON DATABASE :"database_name"
    FROM PUBLIC;

GRANT CONNECT
    ON DATABASE :"database_name"
    TO :"app_user";
SQL

psql \
    --set ON_ERROR_STOP=1 \
    --username "$POSTGRES_USER" \
    --dbname "$RELAYMAID_DB_NAME" \
    --set migrator_user="$RELAYMAID_MIGRATOR_USER" \
    --set app_user="$RELAYMAID_APP_USER" <<'SQL'
REVOKE CREATE
    ON SCHEMA public
    FROM PUBLIC;

GRANT USAGE
    ON SCHEMA public
    TO :"app_user";

ALTER DEFAULT PRIVILEGES
    FOR ROLE :"migrator_user"
    IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE
    ON TABLES
    TO :"app_user";

ALTER DEFAULT PRIVILEGES
    FOR ROLE :"migrator_user"
    IN SCHEMA public
    GRANT USAGE, SELECT
    ON SEQUENCES
    TO :"app_user";
SQL