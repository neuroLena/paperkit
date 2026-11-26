"""Draft parsing shared by all gates."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..schemas import ClaimTable, PaperSpec, SectionSpec

CLAIM_TAG = re.compile(r"<!--\s*(C\d+(?:\s*,\s*C\d+)*)\s*-->")
COMMENT = re.compile(r"<!--.*?-->", re.S)
CITE = re.compile(r"\[([^\[\]]*@[^\[\]]+)\]")
CITE_KEY = re.compile(r"@([A-Za-z0-9_][\w:.#$%&+?<>~/-]*)")
HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$", re.M)
MARKER = re.compile(r"\[(?:AUTHOR|NEEDS SOURCE):[^\]]*\]")
FACT = re.compile(r"\{\{F\w+\}\}")


@dataclass
class GateContext:
    spec: PaperSpec
    sec: SectionSpec
    claims: ClaimTable
    facts: dict
    bib_keys: set[str]
    rules: list = field(default_factory=list)      # approved writing rules for this section


def headings(md: str) -> list[str]:
    return [title for _, title in HEADING.findall(md)]


def paragraphs(md: str) -> list[tuple[str, list[str]]]:
    """Paragraphs without headings: (text, claim ids from its tags)."""
    out = []
    for block in re.split(r"\n\s*\n", md.strip()):
        text = "\n".join(line for line in block.splitlines() if not line.lstrip().startswith("#")).strip()
        if not text:
            continue
        ids: list[str] = []
        for m in CLAIM_TAG.finditer(text):
            ids += [x.strip() for x in m.group(1).split(",")]
        out.append((text, ids))
    return out


def plain(md: str) -> str:
    """Text without tags, citations, placeholders and heading marks: for counting words and finding digits."""
    text = COMMENT.sub("", md)
    text = CITE.sub("", text)
    text = FACT.sub("", text)
    text = MARKER.sub("", text)
    return re.sub(r"^#{1,6}[ \t]+", "", text, flags=re.M)


def cite_keys(md: str) -> set[str]:
    keys: set[str] = set()
    for m in CITE.finditer(md):
        keys |= {k.rstrip(".,;:") for k in CITE_KEY.findall(m.group(1))}
    return keys


def short(text: str, n: int = 90) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"
