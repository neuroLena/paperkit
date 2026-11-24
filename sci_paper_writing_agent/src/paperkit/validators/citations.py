"""Citations: [@key] only, and the key is in library.bib and in the approved claim table."""
from __future__ import annotations

import re

from ..schemas import Issue
from .common import COMMENT, GateContext, cite_keys, short

# "(Smith, 2020)", "(Smith et al. 2020)" and a bare "Smith et al."
TEXTUAL = re.compile(r"\([A-Z][^()\[\]]*?\b(?:19|20)\d{2}[a-z]?\)|\b[A-Z][A-Za-z'-]+ et al\.?")
NEEDS_SOURCE = re.compile(r"\[NEEDS SOURCE:[^\]]*\]")


def check(draft: str, ctx: GateContext) -> list[Issue]:
    issues: list[Issue] = []
    used = cite_keys(draft)
    allowed = {key for c in ctx.claims.claims for key in c.cite_keys}
    for key in sorted(used - ctx.bib_keys):
        issues.append(Issue(gate="citations", message=f"Citation key not in library.bib: {key}"))
    for key in sorted((used & ctx.bib_keys) - allowed):
        issues.append(Issue(gate="citations", message=f"Citation not in the approved claim table: {key}"))
    for m in TEXTUAL.finditer(COMMENT.sub("", draft)):
        issues.append(Issue(gate="citations", message="Citation typed by hand: use [@key]", excerpt=short(m.group(0))))
    for m in NEEDS_SOURCE.finditer(draft):
        issues.append(Issue(gate="citations", severity="warning", message="Source missing from the library",
                            excerpt=short(m.group(0))))
    return issues
