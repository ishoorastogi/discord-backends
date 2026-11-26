#!/usr/bin/env bash
set -euo pipefail

case "${1:-}" in
    -h|--help)
        cat <<'USAGE'
Usage: ./installer.sh

Create or reuse the repository's .venv, install backend and test packages,
cache the models used for local inference, and initialize internships/src/.env.
Requires Python 3.10 or newer. Set PYTHON_BIN to choose an interpreter for a new
virtual environment. The installer prints setup links for missing prerequisites.
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

check_python_version() {
    if ! "$1" -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
        printf 'A working Python 3.10 or newer is required for %s.\n' "$1" >&2
        printf 'Install Python from https://www.python.org/downloads/\n' >&2
        exit 1
    fi
}

if [[ ! -x "$VENV_PYTHON" ]]; then
    if ! command -v "$BOOTSTRAP_PYTHON" >/dev/null 2>&1; then
        printf 'Python was not found: %s. Install Python 3.10+ or set PYTHON_BIN.\n' "$BOOTSTRAP_PYTHON" >&2
        printf 'Download Python from https://www.python.org/downloads/\n' >&2
        exit 1
    fi
    check_python_version "$BOOTSTRAP_PYTHON"
    printf 'Creating virtual environment: %s\n' "$VENV_DIR"
    if ! "$BOOTSTRAP_PYTHON" -m venv "$VENV_DIR"; then
        printf 'Could not create .venv. Enable venv support for your Python installation.\n' >&2
        printf 'On Debian or Ubuntu, install the matching python3-venv package.\n' >&2
        printf 'Python venv setup: https://docs.python.org/3/library/venv.html\n' >&2
        exit 1
    fi
fi

check_python_version "$VENV_PYTHON"

if ! "$VENV_PYTHON" -m pip --version >/dev/null 2>&1; then
    if ! "$VENV_PYTHON" -m ensurepip --upgrade; then
        printf 'Could not install pip. See https://pip.pypa.io/en/stable/installation/\n' >&2
        exit 1
    fi
fi

# Run pip from the repository root so relative requirements stay predictable.
cd "$PROJECT_ROOT"
if ! "$VENV_PYTHON" -m pip install \
    --requirement "$PROJECT_ROOT/requirements.txt" \
    --editable "$PROJECT_ROOT/internships/resume-pipeline/models" \
    --editable "$PROJECT_ROOT/internships/resume-pipeline/resume-parser[dev]" \
    --editable "$PROJECT_ROOT/internships/resume-pipeline/extraction[dev]"; then
    printf 'Python package installation failed. See the pip error above, then rerun the installer.\n' >&2
    printf 'pip help: https://pip.pypa.io/en/stable/installation/\n' >&2
    printf 'PyTorch platform packages: https://pytorch.org/get-started/locally/\n' >&2
    exit 1
fi

# Verify the scraper dependency in the interpreter used to start the backend.
"$VENV_PYTHON" -c 'from bs4 import BeautifulSoup'

ENV_FILE="$PROJECT_ROOT/internships/src/.env"
if [[ ! -e "$ENV_FILE" && ! -L "$ENV_FILE" ]]; then
    (umask 077; cp "$PROJECT_ROOT/internships/src/.env.example" "$ENV_FILE")
    printf 'Created internships/src/.env from its example.\n'
fi

mkdir -p "$PROJECT_ROOT/internships/data/uploads"

printf '\nPreparing models with Hugging Face access enabled.\n'
if ! "$VENV_PYTHON" -B -m internships.data.install_models; then
    printf 'Online model setup encountered an error. Checking what is already cached.\n' >&2
fi

printf '\nVerifying model setup in offline mode.\n'
setup_status=0
"$VENV_PYTHON" -B -m internships.data.install_models --verify-offline || setup_status=$?

if command -v docker >/dev/null 2>&1; then
    if ! docker compose version >/dev/null 2>&1; then
        printf '\nInstall Docker Compose for the local database.\n'
        printf 'Docker Compose setup: https://docs.docker.com/compose/install/\n'
    fi
else
    printf '\nInstall Docker with Compose if you need the local PostgreSQL/pgvector database.\n'
    printf 'Docker setup: https://docs.docker.com/get-docker/\n'
fi
printf 'Local database setup: %s/db/README.md\n' "$PROJECT_ROOT"

if (( setup_status != 0 )); then
    printf '\nPython packages installed. Finish the model or dataset setup above and rerun the installer.\n' >&2
    exit "$setup_status"
fi

printf '\nBackend setup complete. Activate the environment:\n  source %q\n' "$VENV_DIR/bin/activate"
printf '\nStart the backend:\n  %q %q\n' "$VENV_PYTHON" "$PROJECT_ROOT/internships/src/main.py"
printf '\nRun tests:\n  cd %q && %q -m pytest\n' "$PROJECT_ROOT" "$VENV_PYTHON"
