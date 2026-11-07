"""Legge il materiale di un corso da data/<corso>/{slides,exams} e lo spezza in Chunk.

Configurazione facoltativa in data/<corso>/config.json, per esempio
{"exams_from": "2019-06", "exams_from_note": "prima del 2019-06 gli esami sono su x86"}:
gli esami con data nel nome del file (YYYY_MM...) precedenti vengono esclusi se il filtro è attivo.
I file non vengono mai cancellati."""
import json
import re
from collections.abc import Callable
from pathlib import Path

from .models import Chunk

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
WARNINGS: list[str] = []  # problemi di lettura dei file, mostrati nella UI

POINTS_RE = re.compile(r"\((\d+(?:[.,]\d+)?)\s*punt", re.I)
DATE_RE = re.compile(r"^(\d{4})_(\d{1,2})")


def _pdf_pages(path: Path) -> list[str]:
    try:
        from pypdf import PdfReader
    except ImportError:
        msg = "pypdf non installato: i PDF non si possono leggere (pip install -r requirements.txt)"
        if msg not in WARNINGS:
            WARNINGS.append(msg)
        return []
    try:
        return [p.extract_text() or "" for p in PdfReader(str(path)).pages]
    except Exception as e:
        WARNINGS.append(f"{path.name}: {type(e).__name__}: {str(e)[:120]}")
        return []


def _md_blocks(path: Path, exam: bool) -> list[str]:
    text = path.read_text(encoding="utf-8")
    parts = re.split(r"\n(?=##\s)", text) if exam else re.split(r"\n-{3,}\n", text)
    return [p.strip() for p in parts if p.strip()]


def _pdf_exam_points(pages: list[str]) -> list[float]:
    """Euristica economica per i temi PoliTo: domande chiuse = 1, aperte = 5, esercizio 'sino a N punti' = N.
    La sezione corrente vale anche per le pagine seguenti finché non ne inizia un'altra."""
    out, current = [], 1.0
    for text in pages:
        low = text.lower()
        m = re.search(r"sino a (\d+) punti(?! per ogni)", low)
        if m:
            current = float(m.group(1))
        elif "risposta aperta" in low:
            current = 5.0
        elif "risposta chiusa" in low:
            current = 1.0
        out.append(current)
    return out


def course_config(course_dir: str) -> dict:
    p = Path(course_dir) / "config.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:
        return {}


def exam_date(name: str) -> str | None:
    """Data "YYYY-MM" dal nome del file d'esame. Formati: YYYY_MM_..., YYYYMMDD, DDMMYY (es. 040723 = 4/7/2023)."""
    m = DATE_RE.match(name)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    m = re.match(r"^(\d{4})(\d{2})(\d{2})(?!\d)", name)
    if m and m.group(1).startswith(("19", "20")) and 1 <= int(m.group(2)) <= 12 and 1 <= int(m.group(3)) <= 31:
        return f"{m.group(1)}-{m.group(2)}"
    m = re.match(r"^(\d{2})(\d{2})(\d{2})(?!\d)", name)
    if m and 1 <= int(m.group(1)) <= 31 and 1 <= int(m.group(2)) <= 12:
        return f"20{m.group(3)}-{m.group(2)}"
    return None


def course_path(course: str) -> Path:
    return DATA_DIR / course


def list_courses(root: str | Path = DATA_DIR) -> list[str]:
    """Corsi con almeno un file supportato di materiale didattico."""
    def has_material(p: Path) -> bool:
        supported = {".md", ".pdf", ".pptx", ".docx", ".txt"}
        return any(
            f.is_file() and f.suffix.lower() in supported
            and "materials_update_bench" not in f.parts
            and "new_slides" not in f.parts
            and f.name.lower() not in {"programma.txt", "requisiti_attesi.txt", "syllabus.md"}
            for f in p.rglob("*")
        )
    root = Path(root)
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir() and has_material(p))


def load_course(
    course_dir: str | Path,
    exams_from: str | None = None,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> list[Chunk]:
    """`exams_from` ("YYYY-MM"): esclude gli esami più vecchi, se la data è nel nome del file."""
    base = Path(course_dir)
    chunks: list[Chunk] = []
    files_to_load = [
        (folder, file)
        for folder in ("slides", "exercises", "exams")
        for file in sorted((base / folder).glob("*"))
        if file.suffix.lower() in {".pdf", ".md"}
        and not (folder == "exams" and exams_from and (date := exam_date(file.name)) and date < exams_from)
    ]
    total_files = len(files_to_load)
    loaded_files = 0

    def report_file(folder: str, file: Path) -> None:
        nonlocal loaded_files
        loaded_files += 1
        if on_progress:
            on_progress(loaded_files, total_files, f"{folder}/{file.name}")

    if on_progress:
        on_progress(0, total_files, "Preparazione caricamento")
    for f in sorted((base / "slides").glob("*")):
        if f.suffix.lower() == ".pdf":
            for i, page in enumerate(_pdf_pages(f)):
                if page.strip():
                    chunks.append(Chunk(id=f"slides/{f.name}#{i}", source="slide", ref=f"{f.stem} p.{i + 1}", text=page))
            report_file("slides", f)
        elif f.suffix.lower() == ".md":
            for i, block in enumerate(_md_blocks(f, exam=False)):
                chunks.append(Chunk(id=f"slides/{f.name}#{i}", source="slide", ref=f"{f.stem} slide {i + 1}", text=block))
            report_file("slides", f)
    for f in sorted((base / "exercises").glob("*")):  # esercitazioni (facoltative)
        if f.suffix.lower() == ".pdf":
            for i, page in enumerate(_pdf_pages(f)):
                if page.strip():
                    chunks.append(Chunk(id=f"exercises/{f.name}#{i}", source="exercise",
                                        ref=f"{f.stem} p.{i + 1}", text=page))
            report_file("exercises", f)
        elif f.suffix.lower() == ".md":
            for i, block in enumerate(_md_blocks(f, exam=False)):
                chunks.append(Chunk(id=f"exercises/{f.name}#{i}", source="exercise",
                                    ref=f"{f.stem}, esercizio {i + 1}", text=block))
            report_file("exercises", f)
    for f in sorted((base / "exams").glob("*")):
        d = exam_date(f.name)
        if exams_from and d and d < exams_from:
            continue
        if f.suffix.lower() == ".pdf":
            pages = _pdf_pages(f)
            for i, (page, pts) in enumerate(zip(pages, _pdf_exam_points(pages))):
                if page.strip():
                    chunks.append(Chunk(id=f"exams/{f.name}#{i}", source="exam", ref=f"{f.stem} p.{i + 1}",
                                        text=page, points=pts))
            report_file("exams", f)
        elif f.suffix.lower() == ".md":
            for i, block in enumerate(_md_blocks(f, exam=True)):
                if block.startswith("# "):  # intestazione del tema d'esame, non un esercizio
                    continue
                m = POINTS_RE.search(block.splitlines()[0])
                pts = float(m.group(1).replace(",", ".")) if m else 1.0
                chunks.append(Chunk(id=f"exams/{f.name}#{i}", source="exam",
                                    ref=f"{f.stem}, esercizio {i}", text=block, points=pts))
            report_file("exams", f)
    if on_progress:
        on_progress(total_files, total_files, "Caricamento completato")
    return chunks
