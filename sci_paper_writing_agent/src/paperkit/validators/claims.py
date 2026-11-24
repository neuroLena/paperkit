"""Gate for the claim table: runs before a person or the writer sees it."""
from __future__ import annotations

import re

from ..schemas import ClaimTable, Issue


def check_claims(table: ClaimTable, fact_reg: dict, bib_keys: set[str]) -> list[Issue]:
    issues: list[Issue] = []

    def add(message: str, claim_id: str = "") -> None:
        issues.append(Issue(gate="claims", message=message, excerpt=claim_id))

    if not table.claims:
        add("Claim table is empty")
    seen: set[str] = set()
    for c in table.claims:
        if not re.fullmatch(r"C\d+", c.id):
            add(f"Bad claim id '{c.id}': expected C1, C2, ...", c.id)
        if c.id in seen:
            add(f"Duplicate claim id {c.id}", c.id)
        seen.add(c.id)
        for fid in c.fact_ids:
            if fid not in fact_reg:
                add(f"{c.id}: fact id not in facts.json: {fid}", c.id)
        for key in c.cite_keys:
            if key not in bib_keys:
                add(f"{c.id}: citation key not in library.bib: {key}", c.id)
        if c.category == "OBSERVED" and not c.fact_ids:
            add(f"{c.id}: an OBSERVED claim needs at least one fact id", c.id)
    return issues
