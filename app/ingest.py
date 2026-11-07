"""Legge il materiale di un corso da data/<corso>/{slides,exams} e lo spezza in Chunk."""
import re
from pathlib import Path

from .models import Chunk

POINTS_RE = re.compile(r"\((\d+(?:[.,]\d+)?)\s*punt", re.I)


def _read(path: Path) -> list[str]:
    """Restituisce i blocchi di un file: separati da '---' (md) o pagine (pdf)."""
    if path.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            return []
        return [p.extract_text() or "" for p in PdfReader(str(path)).pages]
    text = path.read_text(encoding="utf-8")
    if path.parent.name == "exams":
        parts = re.split(r"\n(?=##\s)", text)
    else:
        parts = re.split(r"\n-{3,}\n", text)
    return [p.strip() for p in parts if p.strip()]


def list_courses(root: str = "data") -> list[str]:
    """Corsi con almeno un file di materiale (le cartelle ancora vuote non compaiono)."""
    def has_material(p: Path) -> bool:
        return any(f.suffix.lower() in (".md", ".pdf") for d in ("slides", "exams") for f in (p / d).glob("*"))
    return sorted(p.name for p in Path(root).iterdir() if p.is_dir() and has_material(p))


def load_course(course_dir: str) -> list[Chunk]:
    base = Path(course_dir)
    chunks: list[Chunk] = []
    n = 0
    for f in sorted((base / "slides").glob("*")):
        for i, block in enumerate(_read(f)):
            n += 1
            chunks.append(Chunk(id=f"slides/{f.name}#{i}", source="slide", ref=f"Slide {n}", text=block))
    for f in sorted((base / "exams").glob("*")):
        for i, block in enumerate(_read(f)):
            if block.startswith("# "):  # intestazione del tema d'esame, non un esercizio
                continue
            m = POINTS_RE.search(block.splitlines()[0])
            pts = float(m.group(1).replace(",", ".")) if m else 1.0
            chunks.append(Chunk(id=f"exams/{f.name}#{i}", source="exam",
                                ref=f"{f.stem}, esercizio {i}", text=block, points=pts))
    return chunks
