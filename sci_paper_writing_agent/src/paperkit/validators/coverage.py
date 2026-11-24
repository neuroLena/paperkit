"""Coverage: every paragraph is tied to a claim, and every claim is used."""
from __future__ import annotations

from .. import facts
from ..schemas import Issue
from .common import GateContext, paragraphs, short


def check(draft: str, ctx: GateContext) -> list[Issue]:
    issues: list[Issue] = []
    known = {c.id: c for c in ctx.claims.claims}
    facts_seen: dict[str, set[str]] = {}

    for text, ids in paragraphs(draft):
        if not ids:
            issues.append(Issue(gate="coverage", message="Paragraph without a claim tag <!-- Cn -->",
                                excerpt=short(text)))
        for cid in ids:
            if cid not in known:
                issues.append(Issue(gate="coverage", message=f"Unknown claim id in tag: {cid}", excerpt=short(text)))
            else:
                facts_seen.setdefault(cid, set()).update(facts.used(text))

    for cid, claim in known.items():
        if cid not in facts_seen:
            issues.append(Issue(gate="coverage", message=f"Claim not used in the draft: {cid}", excerpt=claim.text))
        elif claim.category == "OBSERVED" and claim.fact_ids and not facts_seen[cid] & set(claim.fact_ids):
            issues.append(Issue(gate="coverage", excerpt=claim.text,
                                message=f"{cid} is OBSERVED but its paragraph shows none of its facts {claim.fact_ids}"))
    return issues
