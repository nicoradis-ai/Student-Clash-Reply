"""Materials Update Agent.

La fase di modernizzazione è deterministica: il testo non viene riscritto e le
immagini vengono copiate dai blob originali. L'LLM entra solo nella fase 2,
quando il professore chiede micro-modifiche.
"""
from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

from .llm import chat_json


@dataclass
class SlideBlock:
    source_shape_index: int
    text: str
    left: int
    top: int
    width: int
    height: int
    is_title: bool = False


@dataclass
class SlideAsset:
    number: int
    source_path: str
    title: str
    blocks: list[SlideBlock] = field(default_factory=list)
    image_shapes: list[int] = field(default_factory=list)
    plain_text: str = ""

    @property
    def text(self) -> str:
        return self.plain_text or "\n\n".join(block.text for block in self.blocks if block.text.strip())


@dataclass
class LessonAsset:
    name: str
    source_path: str
    bench_path: str
    slides: list[SlideAsset]
    subtopics: list[str]
    source_format: str = "pptx"


@dataclass
class MicroChange:
    id: str
    lesson: str
    slide_number: int
    original_text: str
    proposed_text: str
    justification: str
    status: str = "pending"


@dataclass
class MaterialsPackage:
    data_dir: str
    lessons: list[LessonAsset]
    syllabus: str
    expected: str
    output_dir: str


LESSON_SUMMARY_SYSTEM = (
    "Sei un assistente didattico. Riassumi una lezione universitaria usando solo il testo fornito. "
    "Restituisci una lista ordinata e schematica di 3-10 sottoargomenti. "
    "Rispondi JSON: {\"subtopics\": [\"...\"]}. Non inventare argomenti."
)

MICRO_CHANGE_SYSTEM = (
    "Sei un assistente didattico. Devi proporre SOLO PICCOLE MODIFICHE: correzioni di errori, "
    "aggiornamenti di tecnologie obsolete o integrazioni fondamentali previste dal programma. "
    "NON stravolgere la slide e non riscrivere l'intero corso. Usa conoscenza generale quando utile, "
    "ma non affermare dettagli non verificabili. Rispondi solo JSON nel formato "
    "{\"changes\": [{\"original_text\": \"...\", \"proposed_text\": \"...\", "
    "\"justification\": \"...\"}]}. Se non serve cambiare nulla, restituisci una lista vuota."
)


def _read_first(data_dir: Path, names: tuple[str, ...]) -> str:
    for name in names:
        matches = list(data_dir.rglob(name))
        if matches:
            return matches[0].read_text(encoding="utf-8-sig")
    return ""


def _sort_key(path: Path):
    name = path.stem.lower()
    number = re.search(r"(?:lezione|lesson|slide)?\s*(\d+)", name)
    date = re.search(r"(20\d{2})[-_](\d{1,2})[-_](\d{1,2})", name)
    if number:
        return (0, int(number.group(1)), name)
    if date:
        return (1, *(int(value) for value in date.groups()), name)
    return (2, name)


def _safe_name(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9À-ÿ]+", "_", text).strip("_")
    return text or "Lezione"


def _title_from_slide(slide) -> str:
    for shape in slide.shapes:
        if not getattr(shape, "has_text_frame", False):
            continue
        if shape.is_placeholder and shape.placeholder_format.idx == 0:
            return shape.text.strip().splitlines()[0][:120]
    for shape in slide.shapes:
        if getattr(shape, "has_text_frame", False) and shape.text.strip():
            return shape.text.strip().splitlines()[0][:120]
    return ""


def _extract_presentation(path: Path) -> list[SlideAsset]:
    presentation = Presentation(str(path))
    slides = []
    for number, slide in enumerate(presentation.slides, 1):
        blocks = []
        images = []
        for index, shape in enumerate(slide.shapes):
            if getattr(shape, "shape_type", None) == MSO_SHAPE_TYPE.PICTURE:
                images.append(index)
            if not getattr(shape, "has_text_frame", False) or not shape.text.strip():
                continue
            blocks.append(SlideBlock(
                source_shape_index=index,
                text=shape.text,
                left=shape.left,
                top=shape.top,
                width=shape.width,
                height=shape.height,
                is_title=bool(shape.is_placeholder and shape.placeholder_format.idx == 0),
            ))
        slides.append(SlideAsset(number, str(path), _title_from_slide(slide), blocks, images))
    return slides


def _extract_document(path: Path) -> list[SlideAsset]:
    """Estrae unità revisionabili da PDF, DOCX, Markdown e testo semplice."""
    suffix = path.suffix.lower()
    pages: list[str] = []
    if suffix == ".pdf":
        from pypdf import PdfReader
        pages = [page.extract_text() or "" for page in PdfReader(str(path)).pages]
    elif suffix == ".docx":
        from docx import Document
        document = Document(str(path))
        paragraphs = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
        paragraphs.extend(" | ".join(cell.text for cell in row.cells) for table in document.tables for row in table.rows)
        pages = ["\n".join(paragraphs)]
    elif suffix == ".md":
        content = path.read_text(encoding="utf-8-sig")
        pages = re.split(r"\n\s*(?:-{3,}|_{3,}|\*{3,})\s*\n", content)
        if len(pages) == 1:
            pages = re.split(r"(?=^#{1,2}\s)", content, flags=re.M)
    elif suffix == ".txt":
        content = path.read_text(encoding="utf-8-sig")
        pages = content.split("\f")
        if len(pages) == 1:
            pages = [content]
    else:
        return []

    assets = []
    for number, text in enumerate(pages, 1):
        text = text.strip()
        title_match = re.search(r"^\s{0,3}#{1,6}\s+(.+)$", text, re.M)
        title = title_match.group(1).strip() if title_match else f"{path.stem} · unità {number}"
        assets.append(SlideAsset(number, str(path), title, plain_text=text))
    return assets


def _offline_subtopics(slides: list[SlideAsset]) -> list[str]:
    topics = []
    for slide in slides:
        title = slide.title.strip()
        if title and title.lower() not in {topic.lower() for topic in topics}:
            topics.append(title)
    return topics or [f"Contenuti slide {slide.number}" for slide in slides]


def _summarize(slides: list[SlideAsset], syllabus: str, expected: str) -> list[str]:
    material = "\n\n".join(f"Slide {slide.number}: {slide.text}" for slide in slides)
    data = chat_json(
        LESSON_SUMMARY_SYSTEM,
        f"Programma:\n{syllabus}\n\nRequisiti attesi:\n{expected}\n\nLezione:\n{material}",
        lambda: {"subtopics": _offline_subtopics(slides)},
    )
    values = [str(value).strip() for value in data.get("subtopics", []) if str(value).strip()]
    return list(dict.fromkeys(values)) or _offline_subtopics(slides)


def _add_text(slide, block: SlideBlock, text: str, slide_width: int):
    textbox = slide.shapes.add_textbox(block.left, block.top, block.width, block.height)
    frame = textbox.text_frame
    frame.clear()
    frame.word_wrap = True
    lines = text.splitlines() or [""]
    for index, line in enumerate(lines):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.text = line
        paragraph.level = 0
        paragraph.font.name = "Aptos"
        paragraph.font.size = Pt(24 if block.is_title else 18)
        paragraph.font.color.rgb = RGBColor(18, 32, 55)
    if block.is_title:
        frame.paragraphs[0].font.bold = True


def _add_header(slide, slide_width: int, slide_height: int, title: str, number: int):
    header = slide.shapes.add_shape(1, 0, 0, slide_width, Inches(0.82))
    header.fill.solid()
    header.fill.fore_color.rgb = RGBColor(18, 32, 55)
    header.line.fill.background()
    text = slide.shapes.add_textbox(Inches(0.45), Inches(0.18), slide_width - Inches(1), Inches(0.42))
    text.text_frame.text = title or f"Slide {number}"
    paragraph = text.text_frame.paragraphs[0]
    paragraph.font.name = "Aptos Display"
    paragraph.font.bold = True
    paragraph.font.size = Pt(25)
    paragraph.font.color.rgb = RGBColor(255, 255, 255)
    footer = slide.shapes.add_textbox(slide_width - Inches(1), slide_height - Inches(0.35), Inches(0.6), Inches(0.2))
    footer.text_frame.text = str(number)
    footer.text_frame.paragraphs[0].alignment = PP_ALIGN.RIGHT
    footer.text_frame.paragraphs[0].font.size = Pt(10)
    footer.text_frame.paragraphs[0].font.color.rgb = RGBColor(90, 105, 125)


def _modernize(source: Path, output: Path, assets: list[SlideAsset]) -> dict:
    original = Presentation(str(source))
    modern = Presentation()
    modern.slide_width = original.slide_width
    modern.slide_height = original.slide_height
    blank = modern.slide_layouts[6]
    mapping = {}
    for asset in assets:
        target = modern.slides.add_slide(blank)
        _add_header(target, modern.slide_width, modern.slide_height, asset.title, asset.number)
        mapping[str(asset.number)] = {}
        source_slide = original.slides[asset.number - 1]
        for block in asset.blocks:
            _add_text(target, block, block.text, modern.slide_width)
            mapping[str(asset.number)][str(block.source_shape_index)] = len(target.shapes) - 1
        for shape in source_slide.shapes:
            if getattr(shape, "shape_type", None) != MSO_SHAPE_TYPE.PICTURE:
                continue
            try:
                target.shapes.add_picture(shape.image.blob, shape.left, shape.top, shape.width, shape.height)
            except Exception:
                # Un'immagine non leggibile non deve impedire il restyling delle altre slide.
                continue
    output.parent.mkdir(parents=True, exist_ok=True)
    modern.save(str(output))
    return mapping


def prepare_materials(data_dir: str | Path, output_dir: str | Path | None = None) -> MaterialsPackage:
    """Scopre PPTX, PDF, DOCX, Markdown e TXT; il restyling è specifico dei PPTX."""
    root = Path(data_dir)
    output = Path(output_dir) if output_dir else root / "materials_update_bench"
    output.mkdir(parents=True, exist_ok=True)
    # Il bench è generato sotto la cartella dei materiali, ma non deve essere
    # riletto come sorgente al giro successivo.
    output_resolved = output.resolve()
    supported = {".pptx", ".pdf", ".docx", ".md", ".txt"}
    files = sorted(
        (path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in supported
         and output_resolved not in path.resolve().parents
         and path.name.lower() not in {"programma.txt", "requisiti_attesi.txt", "syllabus.md"}),
        key=_sort_key,
    )
    syllabus = _read_first(root, ("programma.txt", "syllabus.md"))
    expected = _read_first(root, ("requisiti_attesi.txt",))
    lessons = []
    for index, source in enumerate(files, 1):
        source_assets = _extract_presentation(source) if source.suffix.lower() == ".pptx" else _extract_document(source)
        if not source_assets:
            continue
        label = _safe_name(source.stem)
        ordered_name = f"{index}_{label}{source.suffix.lower()}"
        ordered = output / "ordered" / ordered_name
        ordered.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, ordered)
        bench = output / "bench" / ordered_name
        bench.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix.lower() == ".pptx":
            mapping = _modernize(source, bench, source_assets)
            (bench.with_suffix(".mapping.json")).write_text(json.dumps(mapping, indent=2), encoding="utf-8")
        else:
            shutil.copy2(source, bench)
        lessons.append(LessonAsset(
            name=ordered_name.removesuffix(source.suffix.lower()),
            source_path=str(source),
            bench_path=str(bench),
            slides=source_assets,
            subtopics=_summarize(source_assets, syllabus, expected),
            source_format=source.suffix.lower().lstrip("."),
        ))
    manifest = {
        "lessons": [lesson.name for lesson in lessons],
        "syllabus_file": bool(syllabus),
        "expected_file": bool(expected),
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return MaterialsPackage(str(root), lessons, syllabus, expected, str(output))


def suggest_micro_changes(lesson: LessonAsset, slide: SlideAsset, syllabus: str, expected: str) -> list[MicroChange]:
    """Chiede all'LLM micro-modifiche per una slide, senza alterarla automaticamente."""
    data = chat_json(
        MICRO_CHANGE_SYSTEM,
        f"Programma:\n{syllabus}\n\nRequisiti attesi:\n{expected}\n\n"
        f"Lezione: {lesson.name}\nSlide {slide.number}:\n{slide.text}",
        lambda: {"changes": []},
    )
    changes = []
    for index, item in enumerate(data.get("changes", []), 1):
        original = str(item.get("original_text", "")).strip()
        proposed = str(item.get("proposed_text", "")).strip()
        reason = str(item.get("justification", "")).strip()
        if original and proposed and reason:
            changes.append(MicroChange(f"{lesson.name}-{slide.number}-{index}", lesson.name, slide.number, original, proposed, reason))
    return changes


def approve_change(package: MaterialsPackage, change: MicroChange) -> bool:
    """Aggiorna solo il file revisionato, mai l'originale."""
    lesson = next((item for item in package.lessons if item.name == change.lesson), None)
    if lesson is None:
        return False
    slide = next((item for item in lesson.slides if item.number == change.slide_number), None)
    if slide is None:
        return False
    replaced = False
    if lesson.source_format == "pptx":
        presentation = Presentation(lesson.bench_path)
        target = presentation.slides[slide.number - 1]
        for shape in target.shapes:
            if not getattr(shape, "has_text_frame", False) or change.original_text not in shape.text:
                continue
            shape.text_frame.text = shape.text.replace(change.original_text, change.proposed_text, 1)
            replaced = True
            break
        if replaced:
            presentation.save(lesson.bench_path)
    elif lesson.source_format in {"md", "txt"}:
        bench = Path(lesson.bench_path)
        content = bench.read_text(encoding="utf-8-sig")
        if change.original_text in content:
            bench.write_text(content.replace(change.original_text, change.proposed_text, 1), encoding="utf-8")
            replaced = True
    elif lesson.source_format == "docx":
        from docx import Document
        document = Document(lesson.bench_path)
        paragraphs = list(document.paragraphs)
        paragraphs.extend(
            paragraph
            for table in document.tables
            for row in table.rows
            for cell in row.cells
            for paragraph in cell.paragraphs
        )
        for paragraph in paragraphs:
            full_text = "".join(run.text for run in paragraph.runs)
            if change.original_text not in full_text:
                continue
            updated = full_text.replace(change.original_text, change.proposed_text, 1)
            if paragraph.runs:
                paragraph.runs[0].text = updated
                for run in paragraph.runs[1:]:
                    run.text = ""
            else:
                paragraph.text = updated
            replaced = True
            break
        if replaced:
            document.save(lesson.bench_path)
    elif lesson.source_format == "pdf":
        # PDF non è riscritto in-place: conserva la pagina originale e genera
        # una copia testuale revisionabile con le modifiche approvate.
        revised = Path(lesson.bench_path).with_suffix(".reviewed.md")
        if not revised.exists():
            body = "\n\n".join(f"## Pagina {item.number}\n\n{item.text}" for item in lesson.slides)
            revised.write_text(f"# {lesson.name} — versione revisionata\n\n{body}\n", encoding="utf-8")
        content = revised.read_text(encoding="utf-8")
        if change.original_text in content:
            revised.write_text(content.replace(change.original_text, change.proposed_text, 1), encoding="utf-8")
            replaced = True
    if replaced:
        change.status = "approved"
    return replaced
