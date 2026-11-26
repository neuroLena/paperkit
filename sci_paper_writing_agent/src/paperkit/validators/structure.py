"""Structure: required headings in order, the word limit, and no action marker left over."""
from __future__ import annotations

import re

from ..schemas import Issue
from .common import GateContext, headings, plain, short

ACTION = re.compile(r"\[(?:WRITE|CHANGE)\b[^\]]*\]|\[KEEP\]")   # marks from inputs/<section>_draft.md


def check(draft: str, ctx: GateContext) -> list[Issue]:
    issues: list[Issue] = []
    found = headings(draft)
    last = -1
    for required in ctx.sec.required_headings:
        if required not in found:
            issues.append(Issue(gate="structure", message=f"Missing required heading: ## {required}"))
            continue
        pos = found.index(required)
        if pos < last:
            issues.append(Issue(gate="structure", message=f"Heading out of order: ## {required}"))
        last = max(last, pos)
    extra = [h for h in found if h not in ctx.sec.required_headings]
    if ctx.sec.required_headings and extra:
        issues.append(Issue(gate="structure", message=f"Headings not in the spec: {extra}"))
    for m in ACTION.finditer(draft):
        issues.append(Issue(gate="structure", message="Action marker left in the draft", excerpt=short(m.group(0))))
    words = len(plain(draft).split())
    if words == 0:
        issues.append(Issue(gate="structure", message="Draft is empty"))
    if words > ctx.sec.max_words:
        issues.append(Issue(gate="structure", message=f"Too long: {words} words, limit {ctx.sec.max_words}"))
    return issues
