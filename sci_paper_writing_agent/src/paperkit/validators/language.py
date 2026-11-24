"""Language: wording matches the study design and the claim category.

The lists below are a starting point. Extend them for your field and your style.
"""
from __future__ import annotations

import re

from ..schemas import Issue
from .common import COMMENT, GateContext, paragraphs, short

IC = re.IGNORECASE
CAUSAL = re.compile(
    r"\b(caus(?:e|es|ed|ing|al)|leads? to|led to|results? in|resulted in|effects? of|"
    r"impact(?:s|ed)?|driv(?:e|es|en|ing)|determin(?:e|es|ed))\b", IC)
HYPE = re.compile(
    r"\b(novel|for the first time|the first to|prov(?:e|es|ed|en)|clearly|undoubtedly|"
    r"robust(?:ly)?|groundbreaking|unprecedented)\b", IC)
NULL = re.compile(r"\bno (?:effect|association|difference|relationship)\b", IC)
FILLER = re.compile(
    r"\b(it is important to note that|it should be noted that|it is worth (?:noting|mentioning) that|"
    r"in order to|very|really|basically)\b", IC)

# The wording a paragraph must contain to show the category of its claim
MARKERS = {
    "INFERRED": re.compile(r"\b(suggest|consistent with|indicat|impl(?:y|ies)|appear|may|might)", IC),
    "ASSUMED": re.compile(r"\bassum", IC),
    "SPECULATIVE": re.compile(r"\b(may|might|could|possib|speculat|hypothes)", IC),
}
HEDGED = {"ASSUMED", "SPECULATIVE"}


def check(draft: str, ctx: GateContext) -> list[Issue]:
    issues: list[Issue] = []
    category = {c.id: c.category for c in ctx.claims.claims}

    for raw, ids in paragraphs(draft):
        text = COMMENT.sub("", raw)
        for term in ctx.spec.term_whitelist:
            text = re.sub(re.escape(term), "", text, flags=IC)
        cats = {category[i] for i in ids if i in category}

        if ctx.spec.design == "observational" and not (cats and cats <= HEDGED):
            for m in CAUSAL.finditer(text):
                issues.append(Issue(gate="language", excerpt=short(text),
                                    message=f"Causal wording in an observational study: '{m.group(0)}'"))
        for m in HYPE.finditer(text):
            issues.append(Issue(gate="language", excerpt=short(text),
                                message=f"Overstated wording: '{m.group(0)}'"))
        for m in NULL.finditer(text):
            issues.append(Issue(gate="language", excerpt=short(text),
                                message=f"'{m.group(0)}': say it was not detected and give the interval"))
        for m in FILLER.finditer(text):
            issues.append(Issue(gate="language", severity="warning", excerpt=short(text),
                                message=f"Filler: '{m.group(0)}'"))
        for cat in sorted(cats & set(MARKERS)):
            if not MARKERS[cat].search(text):
                issues.append(Issue(gate="language", excerpt=short(text),
                                    message=f"Paragraph carries an {cat} claim but is not worded as one"))
    return issues
