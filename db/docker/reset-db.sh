#!/usr/bin/env bash

set -euo pipefail

# Paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DB_DIR="$(dirname "$SCRIPT_DIR")"

COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"
ENV_FILE="$DB_DIR/.env"
BUILD_SCRIPT="$SCRIPT_DIR/build-container.sh"

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

[ -f "$BUILD_SCRIPT" ] || \
    error "Missing build-container.sh."

command -v docker >/dev/null 2>&1 || \
    error "Docker is not installed."

docker info >/dev/null 2>&1 || \
    error "Docker engine is not running."

# Confirm destructive operation
# Confirm destructive operation
echo ""
read -r -p "Are you sure you want to hard reset the container? This cannot be undone. (y/n): " CONFIRM

case "$CONFIRM" in
    y|Y)
        info "Hard reset confirmed."
        ;;
    n|N)
        info "Database reset cancelled."
        exit 0
        ;;
    *)
        error "Invalid input. Please enter y or n."
        ;;
esac

# Stop container and delete database volume
info "Stopping PostgreSQL and removing its database volume..."

compose down -v || \
    error "Failed to remove database volume."

# Rebuild database
info "Reinitializing PostgreSQL..."

"$BUILD_SCRIPT" || \
    error "Database initialization failed."

info "Database reset completed successfully."