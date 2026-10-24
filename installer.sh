#!/usr/bin/env bash
set -euo pipefail

case "${1:-}" in
    -h|--help)
        cat <<'USAGE'
Usage: ./installer.sh

Create or reuse the repository's .venv, install all backend and test
dependencies, and initialize internships/src/.env if it does not exist.
Requires Python 3.10 or newer. Set PYTHON_BIN to choose a Python interpreter.
USAGE
        exit 0
        ;;
    "") ;;
    *)
        printf 'Unknown argument: %s\nRun with --help for usage.\n' "$1" >&2
        exit 2
        ;;
esac

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BOOTSTRAP_PYTHON="${PYTHON_BIN:-python3}"
VENV_DIR="$PROJECT_ROOT/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"

if ! command -v "$BOOTSTRAP_PYTHON" >/dev/null 2>&1; then
    printf 'Python was not found: %s. Install Python 3.10+ or set PYTHON_BIN.\n' "$BOOTSTRAP_PYTHON" >&2
    exit 1
fi

check_python_version() {
    "$1" -c 'import sys; sys.exit("Python 3.10 or newer is required.") if sys.version_info < (3, 10) else None'
}

check_python_version "$BOOTSTRAP_PYTHON"

if [[ ! -x "$VENV_PYTHON" ]]; then
    printf 'Creating virtual environment: %s\n' "$VENV_DIR"
    "$BOOTSTRAP_PYTHON" -m venv "$VENV_DIR"
fi

check_python_version "$VENV_PYTHON"

# Run pip from the repository root so relative requirements stay predictable.
cd "$PROJECT_ROOT"
"$VENV_PYTHON" -m pip install \
    --requirement "$PROJECT_ROOT/requirements.txt" \
    --editable "$PROJECT_ROOT/internships/models" \
    --editable "$PROJECT_ROOT/internships/resume-parser[dev]" \
    --editable "$PROJECT_ROOT/internships/extraction[dev]"

ENV_FILE="$PROJECT_ROOT/internships/src/.env"
if [[ ! -e "$ENV_FILE" && ! -L "$ENV_FILE" ]]; then
    (umask 077; cp "$PROJECT_ROOT/internships/src/.env.example" "$ENV_FILE")
    printf 'Created internships/src/.env from its example.\n'
fi

mkdir -p "$PROJECT_ROOT/internships/data/uploads"

printf '\nSetup complete. Activate the environment:\n  source %q\n' "$VENV_DIR/bin/activate"
printf '\nStart the backend:\n  %q %q\n' "$VENV_PYTHON" "$PROJECT_ROOT/internships/src/main.py"
printf '\nRun tests:\n  cd %q && %q -m pytest\n' "$PROJECT_ROOT" "$VENV_PYTHON"
