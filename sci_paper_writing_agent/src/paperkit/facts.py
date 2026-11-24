"""Facts registry: the only source of numbers in the text.

The writer types {{F12}}; code substitutes the fact text at build time. The model never types a number.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

PLACEHOLDER = re.compile(r"\{\{(F\w+)\}\}")


def load(path: Path) -> dict[str, dict]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def from_csv(csv_path: Path, out_path: Path) -> dict[str, dict]:
    """CSV with columns id,text,source -> facts.json."""
    with csv_path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    facts = {r["id"].strip(): {"text": r["text"].strip(), "source": r["source"].strip()} for r in rows}
    bad = [k for k in facts if not re.fullmatch(r"F\w+", k)]
    if bad:
        raise ValueError(f"Fact ids must look like F1, F2a: {bad}")
    if len(facts) != len(rows):
        raise ValueError("Duplicate fact ids in CSV")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(facts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return facts


def used(text: str) -> set[str]:
    return set(PLACEHOLDER.findall(text))


def render(text: str, facts: dict[str, dict]) -> str:
    """Substitutes known facts. Unknown placeholders are left in place and caught by the build."""
    return PLACEHOLDER.sub(lambda m: facts[m.group(1)]["text"] if m.group(1) in facts else m.group(0), text)
