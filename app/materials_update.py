"""Materials Update Agent.

La fase di modernizzazione è deterministica: il testo non viene riscritto e le
immagini vengono copiate dai blob originali. L'LLM entra solo nella fase 2,
quando il professore chiede micro-modifiche.
"""
from __future__ import annotations

import io
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
    "\"justification\": \"...\"}]}. original_text deve essere una citazione breve, esatta e contigua "
    "copiata dalla slide (preferibilmente una singola riga, massimo 15 parole), così da poterla localizzare. "
    "Se non serve cambiare nulla, restituisci una lista vuota."
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


def _modernize_pdf(source: Path, output: Path) -> None:
    """Aggiunge un trattamento UX leggero senza rasterizzare il contenuto PDF."""
    import pymupdf as fitz

    document = fitz.open(source)
    for page_number, page in enumerate(document, 1):
        rect = page.rect
        page.draw_rect(fitz.Rect(12, 12, rect.width - 12, rect.height - 12),
                       color=(0.84, 0.88, 0.93), width=0.8, overlay=True)
        page.draw_line(fitz.Point(20, 18), fitz.Point(72, 18),
                       color=(0.12, 0.32, 0.62), width=2.5, overlay=True)
        page.insert_text(fitz.Point(rect.width - 42, rect.height - 15), str(page_number),
                         fontsize=8, fontname="helv", color=(0.35, 0.40, 0.48), overlay=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    document.save(output, garbage=4, deflate=True)
    document.close()


def _pdf_candidate_bytes(path: str | Path, page_number: int, original: str, proposed: str) -> bytes | None:
    """Restituisce in memoria un PDF con la sola pagina selezionata aggiornata."""
    import pymupdf as fitz

    document = fitz.open(path)
    try:
        page = document[page_number - 1]
        matches = page.search_for(original)
        if not matches:
            return None
        area = matches[0]
        page.add_redact_annot(area, fill=(1, 1, 1), cross_out=False)
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
        area = fitz.Rect(max(16, area.x0 - 1), max(14, area.y0 - 2),
                         min(page.rect.width - 16, area.x1 + 4),
                         min(page.rect.height - 18, area.y1 + 4))
        size = 11
        while size >= 6:
            spare = page.insert_textbox(area, proposed, fontsize=size, fontname="helv",
                                        color=(0.08, 0.14, 0.23), overlay=True)
            if spare >= 0:
                break
            document.close()
            document = fitz.open(path)
            page = document[page_number - 1]
            retry_matches = page.search_for(original)
            if not retry_matches:
                return None
            page.add_redact_annot(retry_matches[0], fill=(1, 1, 1), cross_out=False)
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
            size -= 1
        if size < 6:
            return None
        return document.tobytes(garbage=4, deflate=True)
    finally:
        document.close()


def _render_text_preview(text: str, title: str) -> bytes:
    from PIL import Image, ImageDraw, ImageFont
    import textwrap

    image = Image.new("RGB", (1200, 675), "#f5f7fb")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((35, 30, 1165, 645), radius=20, fill="white", outline="#d8e0eb", width=2)
    draw.rounded_rectangle((55, 50, 1145, 112), radius=12, fill="#142843")
    draw.text((78, 68), title[:60], font=ImageFont.load_default(size=30), fill="white")
    y = 145
    for line in text.splitlines():
        for part in textwrap.wrap(line, width=92) or [""]:
            if y > 610:
                break
            draw.text((75, y), part, font=ImageFont.load_default(size=22), fill="#142843")
            y += 30
        if y > 610:
            break
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _render_pptx_preview(
    lesson: LessonAsset,
    slide_asset: SlideAsset,
    proposed_text: tuple[str, str] | None = None,
    source_path: str | None = None,
) -> bytes:
    """Renderizza una slide PPTX con immagini e testo in una tela UX coerente."""
    from PIL import Image, ImageDraw, ImageFont

    presentation = Presentation(source_path or lesson.source_path)
    slide = presentation.slides[slide_asset.number - 1]
    width, height = 1280, 720
    scale_x = width / presentation.slide_width
    scale_y = height / presentation.slide_height
    image = Image.new("RGB", (width, height), "#f5f7fb")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width, 84), fill="#142843")
    draw.text((42, 24), slide_asset.title[:65] or f"Slide {slide_asset.number}",
              font=ImageFont.load_default(size=30), fill="white")
    replacement = proposed_text
    replaced = False
    for index, shape in enumerate(slide.shapes):
        x0, y0 = int(shape.left * scale_x), int(shape.top * scale_y)
        x1, y1 = int((shape.left + shape.width) * scale_x), int((shape.top + shape.height) * scale_y)
        if getattr(shape, "shape_type", None) == MSO_SHAPE_TYPE.PICTURE:
            try:
                from PIL import Image as PILImage
                photo = PILImage.open(io.BytesIO(shape.image.blob)).convert("RGB")
                photo.thumbnail((max(1, x1 - x0), max(1, y1 - y0)))
                image.paste(photo, (x0, y0))
            except Exception:
                continue
        elif getattr(shape, "has_text_frame", False) and shape.text.strip():
            text = shape.text
            if replacement and not replaced and replacement[0] in text:
                text = text.replace(replacement[0], replacement[1], 1)
                replaced = True
            draw.rounded_rectangle((x0, y0, x1, y1), radius=8, fill="white", outline="#d8e0eb", width=1)
            draw.multiline_text((x0 + 12, y0 + 10), text, font=ImageFont.load_default(size=20),
                                fill="#142843", spacing=6)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def preview_change(lesson: LessonAsset, slide: SlideAsset, change: MicroChange) -> tuple[bytes, bytes] | None:
    """Immagini prima/dopo della specifica pagina o slide."""
    updated = slide.text.replace(change.original_text, change.proposed_text, 1)
    if lesson.source_format == "pdf":
        import pymupdf as fitz
        base = lesson.bench_path if Path(lesson.bench_path).exists() else lesson.source_path
        candidate = _pdf_candidate_bytes(base, slide.number, change.original_text, change.proposed_text)
        if candidate is None:
            return None
        with fitz.open(base) as current:
            before = current[slide.number - 1].get_pixmap(matrix=fitz.Matrix(1.4, 1.4), alpha=False).tobytes("png")
        with fitz.open(stream=candidate, filetype="pdf") as revised:
            after = revised[slide.number - 1].get_pixmap(matrix=fitz.Matrix(1.4, 1.4), alpha=False).tobytes("png")
        return before, after
    if lesson.source_format == "pptx":
        current_deck = lesson.bench_path if Path(lesson.bench_path).exists() else lesson.source_path
        before = _render_pptx_preview(lesson, slide, source_path=current_deck)
        after = _render_pptx_preview(lesson, slide, (change.original_text, change.proposed_text), current_deck)
        return before, after
    return (
        _render_text_preview(slide.text, f"{lesson.name} · slide {slide.number}"),
        _render_text_preview(updated, f"Anteprima proposta · {lesson.name} · slide {slide.number}"),
    )


def prepare_materials(data_dir: str | Path, output_dir: str | Path | None = None) -> MaterialsPackage:
    """Analizza PPTX, PDF, DOCX, Markdown e TXT senza creare file di output."""
    root = Path(data_dir)
    output = Path(output_dir) if output_dir else root / "new_slides"
    output_resolved = output.resolve()
    supported = {".pptx", ".pdf", ".docx", ".md", ".txt"}
    files = sorted(
        (path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in supported
         and output_resolved not in path.resolve().parents
         and "new_slides" not in path.parts
         and path.name.lower() not in {"programma.txt", "requisiti_attesi.txt", "syllabus.md"}),
        key=_sort_key,
    )
    syllabus = _read_first(root, ("programma.txt", "syllabus.md"))
    expected = _read_first(root, ("requisiti_attesi.txt",))
    lessons = []
    for source in files:
        source_assets = _extract_presentation(source) if source.suffix.lower() == ".pptx" else _extract_document(source)
        if not source_assets:
            continue
        label = _safe_name(source.stem)
        ordered_name = f"{len(lessons) + 1}_{label}{source.suffix.lower()}"
        lessons.append(LessonAsset(
            name=ordered_name.removesuffix(source.suffix.lower()),
            source_path=str(source),
            bench_path=str(output / ordered_name),
            slides=source_assets,
            subtopics=_summarize(source_assets, syllabus, expected),
            source_format=source.suffix.lower().lstrip("."),
        ))
    return MaterialsPackage(str(root), lessons, syllabus, expected, str(output))


def modernize_materials(package: MaterialsPackage) -> None:
    """Crea solo new_slides quando il professore avvia esplicitamente il restyling."""
    output = Path(package.data_dir) / "new_slides"
    output.mkdir(parents=True, exist_ok=True)
    for lesson in package.lessons:
        source = Path(lesson.source_path)
        destination = output / Path(lesson.bench_path).name
        if lesson.source_format == "pptx":
            _modernize(source, destination, lesson.slides)
        elif lesson.source_format == "pdf":
            _modernize_pdf(source, destination)
        else:
            shutil.copy2(source, destination)
        lesson.bench_path = str(destination)
    package.output_dir = str(output)


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
        candidate = _pdf_candidate_bytes(lesson.bench_path, slide.number, change.original_text, change.proposed_text)
        if candidate is not None:
            output_path = Path(lesson.bench_path)
            temporary = output_path.with_suffix(output_path.suffix + ".tmp")
            temporary.write_bytes(candidate)
            temporary.replace(output_path)
            replaced = True
    if replaced:
        change.status = "approved"
    return replaced
