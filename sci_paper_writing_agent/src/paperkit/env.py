"""The shared .env file: one file for every key, in the repository folder (the folder above the project).

Reading and writing go through python-dotenv. Values already set in the environment always win.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values, set_key

_FROM_FILE: dict[str, str] = {}     # what this process took from the file, so a later edit of the file can replace it


def env_path(root: Path) -> Path:
    """<repository>/.env, where the repository is the folder that holds the project folder.

    PAPERKIT_ENV_FILE points somewhere else, for a setup that keeps its keys in another place.
    """
    other = os.environ.get("PAPERKIT_ENV_FILE")
    return Path(other).expanduser() if other else Path(root).resolve().parent / ".env"


def load_env(root: Path) -> list[str]:
    """Loads the variables from the shared .env and returns the names it set or changed.

    Empty values are ignored, so an untouched copy of .env.example changes nothing. A value from the shell
    always wins. The file can be read again at any time: a line you added or changed since then is picked up.
    """
    path = env_path(root)
    if not path.is_file():
        return []
    loaded = []
    for name, value in dotenv_values(path).items():
        if not name or not value:
            continue
        current = os.environ.get(name)
        ours = name in _FROM_FILE and current == _FROM_FILE[name]      # set by an earlier read, untouched since
        if not current or (ours and current != value):
            os.environ[name] = _FROM_FILE[name] = value
            loaded.append(name)
    return loaded


def save_env(root: Path, name: str, value: str) -> Path:
    """Sets one variable in the shared .env, keeps its other lines, and limits the file to its owner."""
    path = env_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    set_key(str(path), name, value, quote_mode="never")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def gitignore_path(root: Path) -> Path:
    return env_path(root).parent / ".gitignore"


def is_ignored(root: Path) -> bool:
    """True if the repository's .gitignore already keeps .env out of git."""
    path = gitignore_path(root)
    rules = {line.strip() for line in path.read_text(encoding="utf-8").splitlines()} if path.is_file() else set()
    return bool(rules & {".env", "/.env", "**/.env"})


def ignore(root: Path) -> Path:
    """Adds .env to the repository's .gitignore."""
    path = gitignore_path(root)
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    path.write_text(text + ("\n" if text and not text.endswith("\n") else "") + ".env\n", encoding="utf-8")
    return path
