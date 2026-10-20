#!/usr/bin/env bash

set -euo pipefail

# Paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DB_DIR="$(dirname "$SCRIPT_DIR")"

COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"
ENV_FILE="$DB_DIR/.env"
ENV_EXAMPLE="$DB_DIR/.env.example"

# Logging
info() {
    echo "[INFO] $1"
}

error() {
    echo "[ERROR] $1" >&2
    exit 1
}

# Docker Compose helper
compose() {
    docker compose \
        --env-file "$ENV_FILE" \
        -f "$COMPOSE_FILE" \
        "$@"
}

# Check Docker installation
info "Checking Docker installation..."

command -v docker >/dev/null 2>&1 || \
    error "Docker is not installed."

docker compose version >/dev/null 2>&1 || \
    error "Docker Compose is not available."

# Check Docker engine
info "Checking Docker engine..."

docker info >/dev/null 2>&1 || \
    error "Docker engine is not running."

# Check environment configuration
info "Checking database environment..."

if [ ! -f "$ENV_FILE" ]; then
    if [ -f "$ENV_EXAMPLE" ]; then
        cp "$ENV_EXAMPLE" "$ENV_FILE"

        error "Created db/.env from db/.env.example. Configure your credentials and rerun."
    else
        error "Missing db/.env and db/.env.example."
    fi
fi

# Validate Docker Compose
info "Validating Docker Compose configuration..."

compose config --quiet || \
    error "Invalid Docker Compose configuration."

# Validate environment variables
info "Validating database configuration..."

for VAR in POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB; do
    VALUE=$(compose config --format json | python3 -c \
        "import json,sys; print(json.load(sys.stdin)['services']['postgres']['environment'].get('$VAR', ''))")

    if [ -z "$VALUE" ]; then
        error "$VAR is missing or empty."
    fi
done

# Verify schema exists
info "Checking database schema..."

[ -f "$DB_DIR/schema.sql" ] || \
    error "Missing db/schema.sql."

# Start PostgreSQL
info "Starting PostgreSQL container..."

compose up -d --pull always || \
    error "Failed to start PostgreSQL container."

# Get container ID from Compose
CONTAINER=$(compose ps -q postgres)

[ -n "$CONTAINER" ] || \
    error "PostgreSQL container was not created."

# Wait for PostgreSQL
info "Waiting for PostgreSQL to become healthy..."

MAX_ATTEMPTS=60
HEALTHY=false

for ((i=1; i<=MAX_ATTEMPTS; i++)); do

    STATUS=$(docker inspect \
        --format='{{.State.Health.Status}}' \
        "$CONTAINER" 2>/dev/null || true)

    if [ "$STATUS" = "healthy" ]; then
        HEALTHY=true
        break
    fi

    if [ "$STATUS" = "unhealthy" ]; then
        compose logs --tail=50 postgres
        error "PostgreSQL became unhealthy."
    fi

    sleep 2
done

if [ "$HEALTHY" != true ]; then
    compose logs --tail=50 postgres
    error "PostgreSQL failed to become healthy."
fi

info "PostgreSQL is healthy."

# Verify pgvector extension
info "Checking pgvector extension..."

VECTOR_EXISTS=$(docker exec "$CONTAINER" \
    sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
    "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = '\''vector'\'');"' \
    | tr -d '[:space:]')

[ "$VECTOR_EXISTS" = "t" ] || \
    error "pgvector extension is not enabled."

info "pgvector is enabled."

# Verify schema tables
info "Verifying database schema..."

TABLE_COUNT=$(docker exec "$CONTAINER" \
    sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
    "SELECT COUNT(*) FROM information_schema.tables
     WHERE table_schema = '\''public'\''
     AND table_name IN
     ('\''users'\'', '\''resumes'\'', '\''internships'\'',
      '\''matches'\'', '\''finances'\'');"' \
    | tr -d '[:space:]')

if [ "$TABLE_COUNT" != "5" ]; then
    compose logs --tail=50 postgres
    error "Expected 5 database tables, found $TABLE_COUNT."
fi

info "All 5 database tables verified."

info "Database container started successfully."