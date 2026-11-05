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

# Check environment
[ -f "$ENV_FILE" ] || \
    error "Missing db/.env."

command -v docker >/dev/null 2>&1 || \
    error "Docker is not installed."

docker info >/dev/null 2>&1 || \
    error "Docker engine is not running."

# Stop PostgreSQL
info "Stopping PostgreSQL container..."

compose stop postgres || \
    error "Failed to stop PostgreSQL."

info "PostgreSQL stopped successfully."
info "Database data has been preserved."