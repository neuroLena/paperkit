"""Extract page-level text; requires the optional PyMuPDF package."""
from pathlib import Path


def parse_pdf(path: Path) -> list[dict]:
    import pymupdf
    with pymupdf.open(path) as doc:
        return [{"source": str(path), "page": i + 1, "text": page.get_text()}
                for i, page in enumerate(doc)]
