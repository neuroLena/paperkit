"""Numbers: no digits in the text, only {{F..}} placeholders for approved facts."""
from __future__ import annotations

import re

from .. import facts
from ..schemas import Issue
from .common import GateContext, plain

TOKEN_WITH_DIGIT = re.compile(r"\S*\d\S*")


def check(draft: str, ctx: GateContext) -> list[Issue]:
    issues: list[Issue] = []
    used = facts.used(draft)
    allowed = {fid for c in ctx.claims.claims for fid in c.fact_ids}
    for fid in sorted(used - set(ctx.facts)):
        issues.append(Issue(gate="numbers", message=f"Unknown fact placeholder: {{{{{fid}}}}}"))
    for fid in sorted((used & set(ctx.facts)) - allowed):
        issues.append(Issue(gate="numbers", message=f"Fact not in the approved claim table: {fid}"))

    text = plain(draft)
    for token in ctx.spec.number_whitelist:
        text = text.replace(token, "")
    raw = sorted({m.group(0).strip(".,;:()") for m in TOKEN_WITH_DIGIT.finditer(text)})
    for token in raw[:10]:
        issues.append(Issue(gate="numbers", message="Number typed by hand: use a {{F..}} placeholder", excerpt=token))
    return issues
