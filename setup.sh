#!/usr/bin/env bash
set -euo pipefail

# Usage: bash setup.sh [project_directory] [python_version]
#
# Layout. This folder is the one git repository:
#   .env  .env.example  .gitignore    keys and ignore rules; scaffold.py creates them HERE, never in the project
#   .venv/                            the Python environment (VENV_DIR=/other/path bash setup.sh puts it elsewhere)
#   setup.sh  scaffold.py  publish.sh
#   <project_directory>/              the generated project (default: sci_paper_writing_agent)
#
# To refresh the code in an existing project from a newer scaffold.py: UPDATE_CODE=1 bash setup.sh ...
# The first run makes the first commit; after that, bash publish.sh "what changed" commits and pushes.
# NO_GIT=1 bash setup.sh ... skips git altogether.
PROJECT="${1:-sci_paper_writing_agent}"
PYTHON_VERSION="${2:-3.11}"
cd "$(dirname "$0")"
HERE="$(pwd)"

export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
    echo 'Installing uv...'
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi
command -v uv >/dev/null 2>&1 || { echo 'uv not found on PATH' >&2; exit 1; }
if [ -z "${NO_GIT:-}" ]; then
    command -v git >/dev/null 2>&1 || { echo 'Git must be installed (or run with NO_GIT=1)' >&2; exit 1; }
fi

uv python install "$PYTHON_VERSION"

# Creates the project, and next to it .env (mode 600), .env.example and .gitignore if they are missing.
uv run --no-project --python "$PYTHON_VERSION" scaffold.py "$PROJECT" ${UPDATE_CODE:+--update-code}

# The shared .env holds every key, so it must never be tracked or unignored.
chmod 600 "$HERE/.env" 2>/dev/null || true
if [ -e "$HERE/.git" ]; then
    if git -C "$HERE" ls-files --error-unmatch .env >/dev/null 2>&1 || ! git -C "$HERE" check-ignore -q .env; then
        echo 'ERROR: .env is tracked by git or is not ignored.' >&2
        echo '       Run: git rm --cached .env   and make sure .gitignore has a line with .env' >&2
        exit 1
    fi
fi
if [ -e "$HERE/$PROJECT/.env" ]; then
    echo "Note: $PROJECT/.env is no longer read. Move its keys to $HERE/.env and delete it."
fi

# The virtual environment lives next to setup.sh (in this folder), not inside the project.
VENV="${VENV_DIR:-$HERE/.venv}"
PY="$VENV/bin/python"

# Reuse an existing environment only if it matches the requested Python.
if [ -e "$VENV" ]; then
    if [ ! -x "$PY" ]; then
        echo "Existing $VENV is invalid; rename it before retrying." >&2
        exit 1
    fi
    if ! "$PY" - "$PYTHON_VERSION" <<'PYEOF'
import sys
requested = tuple(map(int, sys.argv[1].split('.')))
raise SystemExit(0 if sys.version_info[:len(requested)] == requested else 1)
PYEOF
    then
        echo "Existing $VENV uses a different Python; rename it before retrying." >&2
        exit 1
    fi
else
    uv venv --python "$PYTHON_VERSION" --seed "$VENV"
fi

# Use the environment interpreter explicitly; no shell activation is required here.
# The project depends on python-dotenv, which reads the shared .env.
"$PY" --version
uv pip install \
    --python "$PY" \
    -e "$HERE/$PROJECT[dev]" \
    "PyMuPDF==1.25.5"

# Run the tests and the paperkit commands from inside the project.
cd "$HERE/$PROJECT"
"$PY" -m pytest -v
"$PY" -m paperkit status

# Show which inputs still need filling in. A new project fails this check by design.
"$PY" -m paperkit check || true

# The folder that holds setup.sh is the repository. Only the first run commits by itself.
if [ -z "${NO_GIT:-}" ]; then
    printf '\nGit repository: %s\n' "$HERE"
    if [ ! -f "$HERE/publish.sh" ]; then
        echo 'publish.sh is missing next to setup.sh, so nothing was committed.'
    elif [ -e "$HERE/.git" ] && git -C "$HERE" rev-parse -q --verify HEAD >/dev/null 2>&1; then
        if [ -n "$(git -C "$HERE" status --porcelain)" ]; then
            echo 'There are uncommitted changes.'
        else
            echo 'Everything is committed.'
        fi
    else
        LOCAL_ONLY=1 bash "$HERE/publish.sh" "Set up $PROJECT" || echo 'The first commit was not made: see the message above.'
    fi
fi

printf '\nSetup complete. Keys go in %s/.env (GitHub for publish.sh, NVIDIA and Anthropic for paperkit),\n' "$HERE"
printf 'or `paperkit start`, menu 9, can save them there for you.\n'
printf '\nTo use the project in your terminal:\n'
printf 'source %q/bin/activate\n' "$VENV"
printf 'cd %q\n' "$HERE/$PROJECT"
printf 'paperkit start    # checklist of inputs, guided fill-in, then a menu of steps\n'
if [ -z "${NO_GIT:-}" ]; then
    printf '\nTo commit and upload this folder to GitHub:\n'
    printf 'bash %q "what changed"\n' "$HERE/publish.sh"
fi