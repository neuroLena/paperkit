#!/usr/bin/env bash
set -euo pipefail

# Commits everything in this folder (setup.sh, scaffold.py, this script and the generated project)
# and pushes it to GitHub. The folder that holds this script is the repository.
#
#   bash publish.sh "what changed"           # commit and push
#   LOCAL_ONLY=1 bash publish.sh "message"   # commit only, no push (setup.sh does this on its first run)
#
# First push: with the GitHub CLI (gh) installed and signed in, the GitHub repository is created
# for you, private, named after this folder. To choose differently:
#   REPO_NAME=my-name VISIBILITY=public bash publish.sh
# Without gh: create an empty repository at https://github.com/new, then
#   git remote add origin https://github.com/<your-user>/<name>.git && bash publish.sh
#
# A project folder in here must not have a .git folder of its own, or git would store it as an
# empty link instead of its files. REMOVE_NESTED_GIT=1 bash publish.sh deletes such leftovers
# (their separate history is lost; the files themselves are kept).

cd "$(dirname "$0")"
HERE="$(pwd)"
MESSAGE="${1:-}"

# Preserve explicitly supplied environment variables
INPUT_GITHUB_USER="${GITHUB_USER:-}"
INPUT_GITHUB_TOKEN="${GITHUB_TOKEN:-}"
INPUT_REPO_NAME="${REPO_NAME:-}"
INPUT_VISIBILITY="${VISIBILITY:-}"

# Load the shared .env that sits next to this script (GITHUB_USER, GITHUB_TOKEN, VISIBILITY, ...)
if [ -f "$HERE/.env" ]; then
    set -a
    source "$HERE/.env"
    set +a
fi

# Explicit environment variables override .env
GITHUB_USER="${INPUT_GITHUB_USER:-${GITHUB_USER:-}}"
GITHUB_TOKEN="${INPUT_GITHUB_TOKEN:-${GITHUB_TOKEN:-}}"
REPO_NAME="${INPUT_REPO_NAME:-${REPO_NAME:-}}"
VISIBILITY="${INPUT_VISIBILITY:-${VISIBILITY:-private}}"

KEY_PATTERN='nvapi-[A-Za-z0-9_-]{20,}|sk-ant-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}'

command -v git >/dev/null 2>&1 || { echo 'Git must be installed.' >&2; exit 1; }
case "$VISIBILITY" in
    private|public) ;;
    *) echo 'VISIBILITY must be private or public.' >&2; exit 1 ;;
esac

# 1. Repositories nested inside this one.
nested="$(find . -mindepth 2 -maxdepth 4 -name .git -not -path './.git/*' -not -path '*/.venv/*' 2>/dev/null || true)"
if [ -n "$nested" ]; then
    if [ -n "${REMOVE_NESTED_GIT:-}" ]; then
        printf '%s\n' "$nested" | while IFS= read -r item; do
            rm -rf -- "$item"
            echo "Removed nested repository data: $item"
        done
    else
        {
            echo 'Not committed. These folders are git repositories of their own,'
            echo 'so this repository cannot store their files:'
            printf '%s\n' "$nested" | sed 's|/\.git$||; s|^\./|    |'
            echo 'If their separate history is not needed, run:'
            echo '    REMOVE_NESTED_GIT=1 bash publish.sh'
        } >&2
        exit 1
    fi
fi

# 2. This folder is the repository.
if [ ! -e .git ]; then
    git init -q -b main . 2>/dev/null || { git init -q . && git symbolic-ref HEAD refs/heads/main; }
    echo "New git repository: $HERE"
fi
prefix="$(git rev-parse --show-prefix)"
if [ -n "$prefix" ]; then
    echo "$HERE is not the top of its own git repository." >&2
    exit 1
fi

# 3. Keys and local clutter stay out, at any depth.
if [ ! -f .gitignore ]; then
    printf '%s\n' '# Keys and local clutter stay out of the repository, at any depth.' \
        '.env' '.venv/' '__pycache__/' '.DS_Store' 'Thumbs.db' > .gitignore
    echo 'Created .gitignore'
fi
# The environment folder is never committed, even if the .gitignore was written earlier without it.
grep -qxE '\.venv/?' .gitignore || { printf '%s\n' '.venv/' >> .gitignore; echo 'Added .venv/ to .gitignore'; }
exposed="$(find . \( -name .git -o -name .venv \) -prune -o -name .env -print 2>/dev/null | while IFS= read -r file; do
    git check-ignore -q "$file" || echo "    $file"
done)"
if [ -n "$exposed" ]; then
    {
        echo 'Not committed. These key files are not ignored by git:'
        echo "$exposed"
        echo 'Add a line with .env to .gitignore, then run this again.'
    } >&2
    exit 1
fi

# 4. A nested repository that was added earlier is stored as a link: drop the link so the files can be added.
git ls-files -s | sed -n 's/^160000 [0-9a-f]* [0-9][[:space:]]//p' | while IFS= read -r link; do
    if [ ! -e "$link/.git" ]; then
        git rm -q --cached -- "$link"
    fi
done

# 5. Stage everything, then make sure no key slipped into a tracked file.
git add -A
if hits="$(git grep --cached -I -l -E "$KEY_PATTERN" 2>/dev/null)" && [ -n "$hits" ]; then
    git reset -q
    {
        echo 'Not committed. These files look like they contain an API key:'
        printf '%s\n' "$hits" | sed 's/^/    /'
        echo 'Move the key to a .env file, then run this again.'
    } >&2
    exit 1
fi

# 6. Commit.
if git diff --cached --quiet; then
    echo 'Nothing new to commit.'
else
    if [ -z "$MESSAGE" ]; then
        if git rev-parse -q --verify HEAD >/dev/null; then
            MESSAGE="Update $(date +%Y-%m-%d)"
        else
            MESSAGE="Set up $REPO_NAME"
        fi
    fi
    if ! git commit -q -m "$MESSAGE"; then
        {
            echo 'The commit failed. If git asked who you are, set your name and email, then run this again:'
            echo '    git config --global user.name "Your Name"'
            echo '    git config --global user.email "you@example.com"'
        } >&2
        exit 1
    fi
    echo "Committed: $(git log --oneline -1)"
fi

# ============================================================
# 7. CREATE REMOTE REPOSITORY AND PUSH
# ============================================================

# Local-only mode: no remote creation or API calls
if [ -n "${LOCAL_ONLY:-}" ]; then
    echo "Local-only mode. Nothing pushed."
    exit 0
fi

# Make sure there is a commit
if ! git rev-parse -q --verify HEAD >/dev/null; then
    echo "There is no commit to push yet."
    exit 0
fi

# ============================================================
# 7.1. PUSH TO EXISTING REMOTE
# ============================================================

if git remote get-url origin >/dev/null 2>&1; then

    echo "Existing GitHub remote:"
    git remote get-url origin

    git push -u origin HEAD

    echo "Pushed to GitHub."
    exit 0

fi

# ============================================================
# 7.2. ASK FOR REPOSITORY NAME
# ============================================================

DEFAULT_REPO_NAME="$(basename "$HERE")"

if [ -z "$REPO_NAME" ]; then

    read -r -p \
        "Enter GitHub repository name [$DEFAULT_REPO_NAME]: " \
        REPO_NAME

    REPO_NAME="${REPO_NAME:-$DEFAULT_REPO_NAME}"

fi

# Validate repository name
if ! [[ "$REPO_NAME" =~ ^[a-zA-Z0-9._-]+$ ]] \
    || [[ "$REPO_NAME" == "." || "$REPO_NAME" == ".." ]] \
    || [ "${#REPO_NAME}" -gt 100 ]; then

    echo "Invalid repository name." >&2
    exit 1

fi

# ============================================================
# 7.3. ASK FOR REPOSITORY VISIBILITY
# ============================================================

read -r -p \
    "Repository visibility (private/public) [$VISIBILITY]: " \
    INPUT_VISIBILITY

VISIBILITY="${INPUT_VISIBILITY:-$VISIBILITY}"

case "$VISIBILITY" in

    private)
        PRIVATE_JSON=true
        ;;

    public)
        PRIVATE_JSON=false
        ;;

    *)
        echo "Visibility must be private or public." >&2
        exit 1
        ;;

esac

# ============================================================
# 7.4. CONFIRM CREATION
# ============================================================

# No GITHUB_USER in .env: take it from the signed-in GitHub CLI
if [ -z "$GITHUB_USER" ] && command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    GITHUB_USER="$(gh api user -q .login 2>/dev/null || true)"
fi

echo ""
echo "Repository to create:"
echo "  Owner:      ${GITHUB_USER:-(the account of the token)}"
echo "  Name:       $REPO_NAME"
echo "  Visibility: $VISIBILITY"
echo ""

read -r -p "Create this repository? [Y/n]: " CONFIRM

case "$CONFIRM" in

    ""|y|Y|yes|YES)
        ;;

    *)
        echo "Repository creation cancelled."
        exit 0
        ;;

esac

# ============================================================
# 7.5. USE GITHUB CLI IF AVAILABLE
# ============================================================

if command -v gh >/dev/null 2>&1 \
    && gh auth status >/dev/null 2>&1; then

    echo "Creating repository using GitHub CLI..."

    gh repo create "${GITHUB_USER:+$GITHUB_USER/}$REPO_NAME" \
        "--$VISIBILITY" \
        --source=. \
        --remote=origin

    if [ -n "$GITHUB_USER" ]; then
        git remote set-url origin \
            "git@github.com:$GITHUB_USER/$REPO_NAME.git"
    fi

    git push -u origin HEAD

    echo "Repository published:"
    echo "https://github.com/$GITHUB_USER/$REPO_NAME"

    exit 0

fi

# ============================================================
# 7.6. GITHUB REST API FALLBACK
# ============================================================

command -v curl >/dev/null 2>&1 || {
    echo "curl must be installed." >&2
    exit 1
}

# Read token without displaying it
if [ -z "${GITHUB_TOKEN:-}" ]; then

    echo "A GitHub Personal Access Token is required."
    echo "Generate one at:"
    echo "https://github.com/settings/tokens/new"

    read -r -s -p "GitHub token: " GITHUB_TOKEN
    echo ""

fi

if [ -z "$GITHUB_TOKEN" ]; then
    echo "No GitHub token provided." >&2
    exit 1
fi

# Verify that the token belongs to the expected user
USER_RESPONSE="$(mktemp)"
API_RESPONSE="$(mktemp)"

trap 'rm -f "$USER_RESPONSE" "$API_RESPONSE"' EXIT

api_request() {
    # Pass the authorization header through stdin rather than
    # exposing the token in curl's command-line arguments.
    printf 'header = "Authorization: Bearer %s"\n' \
        "$GITHUB_TOKEN" |
        curl --config - \
            --silent \
            --show-error \
            --connect-timeout 15 \
            --max-time 60 \
            -H "Accept: application/vnd.github+json" \
            "$@"
}

USER_STATUS="$(api_request \
    -o "$USER_RESPONSE" \
    -w "%{http_code}" \
    https://api.github.com/user)"

if [ "$USER_STATUS" != "200" ]; then

    echo "GitHub authentication failed (HTTP $USER_STATUS)." >&2
    exit 1

fi

TOKEN_USER="$(sed -nE \
    's/^[[:space:]]*"login":[[:space:]]*"([^"]+)".*/\1/p' \
    "$USER_RESPONSE" | head -n 1)"

if [ -z "$GITHUB_USER" ]; then
    GITHUB_USER="$TOKEN_USER"
fi

if [ "$TOKEN_USER" != "$GITHUB_USER" ]; then

    echo "The token belongs to '$TOKEN_USER', not '$GITHUB_USER'." >&2
    exit 1

fi

# ============================================================
# 7.7. CREATE THE REMOTE REPOSITORY
# ============================================================

echo "Creating GitHub repository through REST API..."

PAYLOAD="$(printf \
    '{"name":"%s","private":%s,"auto_init":false}' \
    "$REPO_NAME" \
    "$PRIVATE_JSON")"

HTTP_STATUS="$(api_request \
    -o "$API_RESPONSE" \
    -w "%{http_code}" \
    -X POST \
    -H "Content-Type: application/json" \
    https://api.github.com/user/repos \
    -d "$PAYLOAD")"

unset GITHUB_TOKEN

# ============================================================
# 7.8. CHECK API RESPONSE
# ============================================================

case "$HTTP_STATUS" in

    201)
        echo "GitHub repository created successfully."
        ;;

    401)
        echo "Authentication failed. Check your token." >&2
        exit 1
        ;;

    403)
        echo "Permission denied. Check token permissions." >&2
        exit 1
        ;;

    422)
        echo "Repository creation failed." >&2
        echo "The name may already exist or be invalid." >&2
        cat "$API_RESPONSE" >&2
        exit 1
        ;;

    *)
        echo "GitHub API returned HTTP $HTTP_STATUS." >&2
        cat "$API_RESPONSE" >&2
        exit 1
        ;;

esac

# ============================================================
# 7.9. CONFIGURE SSH REMOTE
# ============================================================

REMOTE_URL="git@github.com:$GITHUB_USER/$REPO_NAME.git"

git remote add origin "$REMOTE_URL"

echo "Remote configured:"
echo "$REMOTE_URL"

# ============================================================
# 7.10. PUSH PROJECT
# ============================================================

git push -u origin HEAD

echo ""
echo "============================================"
echo "PROJECT PUBLISHED SUCCESSFULLY"
echo "============================================"
echo ""
echo "Repository:"
echo "https://github.com/$GITHUB_USER/$REPO_NAME"
echo ""
echo "Local folder:"
echo "$HERE"
echo ""