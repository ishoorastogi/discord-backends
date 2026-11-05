#!/usr/bin/env bash

set -euo pipefail

# Paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DB_DIR="$(dirname "$SCRIPT_DIR")"

COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"
ENV_FILE="$DB_DIR/.env"

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

# Check dependencies
command -v docker >/dev/null 2>&1 || \
    error "Docker is not installed."

docker info >/dev/null 2>&1 || \
    error "Docker engine is not running."

docker compose version >/dev/null 2>&1 || \
    error "Docker Compose is not available."

# Check environment
[ -f "$ENV_FILE" ] || \
    error "Missing db/.env. Run build-container.sh first."

# Find running PostgreSQL container
CONTAINER=$(compose ps -q postgres)

[ -n "$CONTAINER" ] || \
    error "PostgreSQL container not found. Run build-container.sh first."

# Verify container is running
STATUS=$(docker inspect \
    --format='{{.State.Running}}' \
    "$CONTAINER")

[ "$STATUS" = "true" ] || \
    error "PostgreSQL container is not running."

# Connect to database
info "Connecting to PostgreSQL..."
info "Type \\q to exit."

compose exec postgres \
    sh -c 'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'