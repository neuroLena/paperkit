"""Read CSV/TSV cells without converting or rounding numeric strings."""
import csv
from pathlib import Path


def read_table(path: Path) -> list[dict]:
    if path.suffix.lower() not in {".csv", ".tsv"}:
        raise ValueError("Expected CSV or TSV")
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t" if path.suffix.lower() == ".tsv" else ",")
        return list(reader)
