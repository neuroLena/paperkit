"""Where a draft that is over its word limit can be shortened. Counting only: no model is called.

The same numbers are used twice. The report lists them for a person, and the structure gate sends a
short form back to the writer together with the "Too long" problem.
"""
from __future__ import annotations

import re
from collections import Counter

from .validators.common import COMMENT, HEADING, paragraphs, plain, short
from .validators.language import FILLER

LONG_SENTENCE = 35          # words: longer sentences are listed as candidates to trim
THIN_CLAIM = 70             # words per claim: below this the claim table is too large for the limit
KEEP = "[KEEP]"
MARKS = re.compile(r"\[(?:WRITE|CHANGE)\b[^\]]*\]|\[KEEP\]")    # the marks of inputs/<section>_draft.md


def words(md: str) -> int:
    """The count the structure gate uses: no tags, citations, placeholders or heading marks."""
    return len(plain(md).split())


def by_heading(md: str) -> list[tuple[str, int]]:
    """(heading, words under it) in the order of the draft."""
    out: list[tuple[str, int]] = []
    name, rows = "(before the first heading)", []

    def close() -> None:
        count = words("\n".join(rows))
        if count:
            out.append((name, count))

    for line in md.splitlines():
        found = HEADING.match(line)
        if found:
            close()
            name, rows = found.group(2), []
        else:
            rows.append(line)
    close()
    return out


def analyse(draft: str, limit: int) -> dict | None:
    """None when the draft is within the limit. Otherwise how much is over, and where the words are."""
    total = words(draft)
    if total <= limit:
        return None
    paras = [(text, ids, words(text)) for text, ids in paragraphs(draft)]
    in_paragraphs: dict[str, list[int]] = {}
    for _, ids, count in paras:
        for claim_id in dict.fromkeys(ids):
            in_paragraphs.setdefault(claim_id, []).append(count)
    repeated = sorted(((claim_id, len(counts), sum(counts)) for claim_id, counts in in_paragraphs.items()
                       if len(counts) > 1), key=lambda row: -row[2])
    long_sentences = sum(1 for text, _, _ in paras for sentence in re.split(r"(?<=[.!?])\s+", plain(text))
                         if len(sentence.split()) > LONG_SENTENCE)
    filler = Counter(m.group(0).lower() for m in FILLER.finditer(plain(draft)))
    longest = sorted(paras, key=lambda row: -row[2])[:5]
    return {
        "total": total, "limit": limit, "over": total - limit, "percent": round(100 * (total - limit) / total),
        "headings": [(name, count, round(count * limit / total)) for name, count in by_heading(draft)],
        "longest": [(count, ids, short(COMMENT.sub("", text), 80)) for text, ids, count in longest],
        "repeated": repeated, "long_sentences": long_sentences, "filler": filler.most_common(),
    }


def hint(found: dict) -> str:
    """One line for the writer: how much to cut, the target under each heading, and the claims said twice."""
    parts = [f"cut {found['over']} words ({found['percent']}%)"]
    if found["headings"]:
        parts.append("aim per heading: " + "; ".join(f"{name} {now} -> {target}" for name, now, target in found["headings"]))
    if found["repeated"]:
        parts.append("say each claim once: " + ", ".join(row[0] for row in found["repeated"][:8])
                     + " take more than one paragraph")
    return ". ".join(parts)


def own_words(starting_draft: str) -> int:
    """Words of the author's own text in inputs/<section>_draft.md, without its comment and its marks."""
    return words(MARKS.sub("", COMMENT.sub("", starting_draft)))


def kept_words(starting_draft: str) -> int:
    """Words in the paragraphs of inputs/<section>_draft.md that carry a [KEEP] mark."""
    text = COMMENT.sub("", starting_draft)
    return sum(words(MARKS.sub("", block)) for block, _ in paragraphs(text) if KEEP in block)


def report_lines(sec_id: str, source: str, found: dict, claims: int = 0, kept: int = 0, starting: int = 0) -> list[str]:
    """The "Where to shorten" block of build/report.md for one section."""
    limit = found["limit"]
    lines = [f"## Where to shorten: {sec_id}", "",
             f"The latest draft ({source}) has {found['total']} words. The limit is {limit}, "
             f"so {found['over']} words ({found['percent']}%) have to go.", ""]
    if found["headings"]:
        lines += ["Words under each heading, with the target if every heading shrinks by the same share:", "",
                  "| Heading | Now | Target | Cut |", "|---|---|---|---|"]
        lines += [f"| {name} | {now} | {target} | {now - target} |" for name, now, target in found["headings"]]
        lines.append("")
    if found["longest"]:
        lines += ["The longest paragraphs:", ""]
        lines += [f"{n}. {count} words{', claims ' + ', '.join(ids) if ids else ''}: \"{start}\""
                  for n, (count, ids, start) in enumerate(found["longest"], 1)]
        lines.append("")
    if found["repeated"]:
        lines += ["Claims that take more than one paragraph (say each once and cut the repeats):", ""]
        lines += [f"- {claim_id}: {count} paragraphs, {total} words" for claim_id, count, total in found["repeated"]]
        lines.append("")
    more = []
    if claims:
        per_claim = limit // claims
        row = f"The claim table has {claims} claims. At {limit} words that is about {per_claim} words per claim"
        if per_claim < THIN_CLAIM:
            row += (f", less than one short paragraph each: the writer cannot fit them. Delete or merge claims in "
                    f"state/claims/{sec_id}.json (then approve and run again), or raise max_words in paper.yaml")
        more.append(row + ".")
    if kept:
        more.append(f"inputs/{sec_id}_draft.md marks about {kept} words as [KEEP]. The writer must keep them word for word"
                    + (", and that alone is over the limit." if kept > limit else "."))
    if starting > limit:
        more.append(f"Your starting draft in inputs/{sec_id}_draft.md has {starting} words, and the writer follows it. "
                    "Shorten it there, or mark what can go with [CHANGE: shorten].")
    if found["long_sentences"]:
        more.append(f"{found['long_sentences']} sentence(s) have more than {LONG_SENTENCE} words: split or trim them.")
    if found["filler"]:
        more.append("Filler to delete: " + ", ".join(f'"{phrase}" ({count})' for phrase, count in found["filler"][:6]) + ".")
    if more:
        lines += ["Also:", ""] + [f"- {row}" for row in more] + [""]
    return lines[:-1] if lines[-1] == "" else lines
