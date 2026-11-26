"""Writing rules: approved rules that ban specific words or phrases are checked here, in code.

The other approved rules are for the writer and the reviewer, who get them with the section.
"""
from __future__ import annotations

import re

from ..schemas import Issue
from .common import COMMENT, GateContext, paragraphs, short


def check(draft: str, ctx: GateContext) -> list[Issue]:
    rules = [rule for rule in ctx.rules if rule.avoid_terms]
    issues: list[Issue] = []
    if not rules:
        return issues
    for raw, _ in paragraphs(draft):
        text = COMMENT.sub("", raw)
        for term in ctx.spec.term_whitelist:
            text = re.sub(re.escape(term), "", text, flags=re.IGNORECASE)
        for rule in rules:
            for term in rule.avoid_terms:
                if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text, re.IGNORECASE):
                    issues.append(Issue(gate="rules", severity=rule.severity, excerpt=short(text),
                                        message=f"{rule.id}: avoid '{term}' ({rule.instruction})"))
    return issues
