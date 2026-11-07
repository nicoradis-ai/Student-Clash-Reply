"""Materials Update Agent.

La fase di modernizzazione è deterministica: il testo non viene riscritto e le
immagini vengono copiate dai blob originali. L'LLM entra solo nella fase 2,
quando il professore chiede micro-modifiche.
"""
from __future__ import annotations

import io
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE, MSO_SHAPE_TYPE
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
class TableBlock:
    source_shape_index: int
    rows: list[list[str]]
    left: int
    top: int
    width: int
    height: int


@dataclass
class SlideAsset:
    number: int
    source_path: str
    title: str
    blocks: list[SlideBlock] = field(default_factory=list)
    tables: list[TableBlock] = field(default_factory=list)
    image_shapes: list[int] = field(default_factory=list)
    plain_text: str = ""

    @property
    def text(self) -> str:
        if self.plain_text:
            return self.plain_text
        text_blocks = [block.text for block in self.blocks if block.text.strip()]
        table_blocks = ["\n".join("\t".join(row) for row in table.rows) for table in self.tables]
        return "\n\n".join(text_blocks + table_blocks)


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
            if getattr(shape, "has_table", False):
                table_text = "\n".join(
                    "\t".join(cell.text for cell in row.cells)
                    for row in shape.table.rows
                )
                if table_text.strip():
                    blocks.append(SlideBlock(
                        source_shape_index=index,
                        text=table_text,
                        left=shape.left,
                        top=shape.top,
                        width=shape.width,
                        height=shape.height,
                    ))
                continue
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
    frame.text = text
    for paragraph in frame.paragraphs:
        paragraph.font.name = "Aptos"
        paragraph.font.size = Pt(24 if block.is_title else 18)
        paragraph.font.color.rgb = RGBColor(18, 32, 55)
        paragraph.font.bold = block.is_title


def _clear_shapes(slide) -> None:
    for shape in list(slide.shapes):
        element = shape._element
        element.getparent().remove(element)


def _add_standard_frame(slide, slide_width: int, slide_height: int) -> None:
    """Cornice senza testo: nessuna parola viene aggiunta alla slide originale."""
    background = slide.background.fill
    background.solid()
    background.fore_color.rgb = RGBColor(255, 255, 255)

    margin = Inches(0.28)
    frame = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        margin,
        margin,
        slide_width - 2 * margin,
        slide_height - 2 * margin,
    )
    frame.fill.solid()
    frame.fill.fore_color.rgb = RGBColor(255, 255, 255)
    frame.line.color.rgb = RGBColor(38, 91, 181)
    frame.line.width = Pt(1.25)

    accent = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.62), Inches(0.55), Inches(1.28), Inches(0.09))
    accent.fill.solid()
    accent.fill.fore_color.rgb = RGBColor(38, 91, 181)
    accent.line.fill.background()


def _copy_picture(target, source_shape) -> None:
    """Ricrea l'immagine esattamente nella sua area, compreso l'eventuale ritaglio."""
    picture = target.shapes.add_picture(
        source_shape.image.blob,
        source_shape.left,
        source_shape.top,
        source_shape.width,
        source_shape.height,
    )
    for attribute in ("crop_left", "crop_right", "crop_top", "crop_bottom"):
        setattr(picture, attribute, getattr(source_shape, attribute, 0.0))


def _recreate_modern_slide(
    slide,
    source_slide,
    asset: SlideAsset,
    slide_width: int,
    slide_height: int,
    replacement: tuple[str, str] | None = None,
) -> bool:
    """Ricostruisce una sola slide con lo stile standard e contenuti originali."""
    if replacement and not any(replacement[0] in block.text for block in asset.blocks):
        return False

    _clear_shapes(slide)
    _add_standard_frame(slide, slide_width, slide_height)
    replaced = False
    blocks_by_shape = {block.source_shape_index: block for block in asset.blocks}
    for index, shape in enumerate(source_slide.shapes):
        block = blocks_by_shape.get(index)
        if block is not None:
            text = block.text
            if replacement and not replaced and replacement[0] in text:
                text = text.replace(replacement[0], replacement[1], 1)
                replaced = True
            _add_text(slide, block, text, slide_width)
        elif getattr(shape, "shape_type", None) == MSO_SHAPE_TYPE.PICTURE:
            try:
                _copy_picture(slide, shape)
            except Exception:
                # Una figura non supportata non impedisce il recupero delle altre immagini.
                continue
    return replaced if replacement else True


def _modernize(
    source: Path,
    output: Path,
    assets: list[SlideAsset],
    on_slide: Callable[[SlideAsset], None] | None = None,
) -> dict:
    original = Presentation(str(source))
    modern = Presentation()
    modern.slide_width = original.slide_width
    modern.slide_height = original.slide_height
    blank = modern.slide_layouts[6]
    mapping = {}
    for asset in assets:
        target = modern.slides.add_slide(blank)
        mapping[str(asset.number)] = {}
        source_slide = original.slides[asset.number - 1]
        _recreate_modern_slide(target, source_slide, asset, modern.slide_width, modern.slide_height)
        if on_slide:
            on_slide(asset)
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
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((27, 27, width - 27, height - 27), radius=22, fill="white", outline="#265bb5", width=3)
    draw.rounded_rectangle((60, 54, 188, 63), radius=5, fill="#265bb5")
    replacement = proposed_text
    replaced = False
    for index, shape in enumerate(slide.shapes):
        x0, y0 = int(shape.left * scale_x), int(shape.top * scale_y)
        x1, y1 = int((shape.left + shape.width) * scale_x), int((shape.top + shape.height) * scale_y)
        if getattr(shape, "shape_type", None) == MSO_SHAPE_TYPE.PICTURE:
            try:
                from PIL import Image as PILImage
                photo = PILImage.open(io.BytesIO(shape.image.blob)).convert("RGB")
                crop_left = int(photo.width * getattr(shape, "crop_left", 0.0))
                crop_top = int(photo.height * getattr(shape, "crop_top", 0.0))
                crop_right = photo.width - int(photo.width * getattr(shape, "crop_right", 0.0))
                crop_bottom = photo.height - int(photo.height * getattr(shape, "crop_bottom", 0.0))
                photo = photo.crop((crop_left, crop_top, crop_right, crop_bottom))
                photo = photo.resize((max(1, x1 - x0), max(1, y1 - y0)))
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


def prepare_materials(
    data_dir: str | Path,
    output_dir: str | Path | None = None,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> MaterialsPackage:
    """Analizza esclusivamente le presentazioni PPTX presenti in ``data_dir/slides``."""
    root = Path(data_dir)
    slides_dir = root / "slides"
    output = Path(output_dir) if output_dir else root / "new_slides"
    files = sorted(
        (path for path in slides_dir.rglob("*") if path.is_file() and path.suffix.lower() == ".pptx"),
        key=_sort_key,
    ) if slides_dir.is_dir() else []
    syllabus = _read_first(root, ("programma.txt", "syllabus.md"))
    expected = _read_first(root, ("requisiti_attesi.txt",))
    lessons = []
    total_files = len(files)
    if on_progress:
        on_progress(0, total_files, "Preparazione analisi")
    for position, source in enumerate(files, 1):
        source_assets = _extract_presentation(source)
        if not source_assets:
            if on_progress:
                on_progress(position, total_files, source.name)
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
        if on_progress:
            on_progress(position, total_files, source.name)
    if on_progress:
        on_progress(total_files, total_files, "Analisi completata")
    return MaterialsPackage(str(root), lessons, syllabus, expected, str(output))


def modernize_materials(
    package: MaterialsPackage,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> None:
    """Ricrea solo i PPTX di ``slides`` in ``new_slides``, una slide alla volta."""
    output = Path(package.data_dir) / "new_slides"
    output.mkdir(parents=True, exist_ok=True)
    ppt_lessons = [lesson for lesson in package.lessons if lesson.source_format == "pptx"]
    total_slides = sum(len(lesson.slides) for lesson in ppt_lessons)
    completed_slides = 0
    if on_progress:
        on_progress(0, total_slides, "Preparazione ricostruzione slide")
    for lesson in ppt_lessons:
        source = Path(lesson.source_path)
        destination = output / Path(lesson.bench_path).name

        def report_slide(asset: SlideAsset) -> None:
            nonlocal completed_slides
            completed_slides += 1
            if on_progress:
                on_progress(
                    completed_slides,
                    total_slides,
                    f"{source.name} · slide {asset.number}/{len(lesson.slides)}",
                )

        _modernize(source, destination, lesson.slides, on_slide=report_slide)
        lesson.bench_path = str(destination)
    package.output_dir = str(output)
    if on_progress:
        on_progress(total_slides, total_slides, "Ricostruzione slide completata")


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


def approve_change(
    package: MaterialsPackage,
    change: MicroChange,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> bool:
    """Rigenera solo la slide approvata nel PPTX modernizzato, mai l'originale."""
    lesson = next((item for item in package.lessons if item.name == change.lesson), None)
    if lesson is None:
        return False
    slide = next((item for item in lesson.slides if item.number == change.slide_number), None)
    if slide is None:
        return False
    replaced = False
    if on_progress:
        on_progress(0, 1, f"Rigenero slide {change.slide_number}")
    if lesson.source_format == "pptx":
        presentation = Presentation(lesson.bench_path)
        source_presentation = Presentation(lesson.source_path)
        target = presentation.slides[slide.number - 1]
        source_slide = source_presentation.slides[slide.number - 1]
        replaced = _recreate_modern_slide(
            target,
            source_slide,
            slide,
            presentation.slide_width,
            presentation.slide_height,
            replacement=(change.original_text, change.proposed_text),
        )
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
    if on_progress:
        result = "Slide ricreata" if replaced else "Testo non trovato: nessuna slide modificata"
        on_progress(1, 1, result)
    return replaced
