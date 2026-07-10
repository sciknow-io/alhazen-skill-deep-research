#!/usr/bin/env python3
"""Lightweight layout-aware PDF article parser (PyMuPDF), porting LA-PDFText's
block-classification methodology (Ramakrishnan et al. 2012): blockify by
font/position, classify blocks with an ordered rule list gated on geometry
and typography (regex only as a secondary disambiguator, never the primary
signal), then assemble reading order column-aware.
"""
import re
import statistics
import sys
from collections import Counter
from dataclasses import dataclass, field

import fitz  # PyMuPDF

BOLD_FLAG = 1 << 4

# Section-name prefixes, used ONLY to *label* a block already classified as a
# heading by geometry (size/boldness/position) — never to detect headingness
# itself. Mirrors LA-PDFText's `^(Intr|INTR)`-style anchors.
SECTION_PATTERNS = [
    ("abstract", r"^(abstract|summary)\b"),
    ("introduction", r"^(introduction|background)\b"),
    ("methods", r"^(materials?\s+and\s+methods?|methods?|methodology)\b"),
    ("results", r"^(results?|observations?)\b"),
    ("discussion", r"^discussion\b"),
    ("conclusion", r"^conclusions?\b"),
    ("references", r"^(references?|bibliography|literature\s+cited)\b"),
    ("acknowledgements", r"^acknowledge?ments?\b"),
    ("funding", r"^funding\b"),
    ("conflict_of_interest", r"^(conflicts?\s+of\s+interest|competing\s+interests?)\b"),
    ("supplementary", r"^(supplementary|supporting\s+information)\b"),
]
# Up to 3 leading non-word chars tolerated: some PDFs prepend a stray glyph
# (ligature/dingbat artifact, e.g. '\x83') directly before the caption text.
# "Extended Data"/"Supplementary" are standardized cross-journal caption
# prefixes (not a journal-specific guess), so they're folded into the same
# robust anchor rather than treated as a separate heuristic.
FIGURE_RE = re.compile(r"^\W{0,3}((extended\s+data|supplementary)\s+)?fig(ure)?\.?\s*\d", re.IGNORECASE)
TABLE_RE = re.compile(r"^\W{0,3}((extended\s+data|supplementary)\s+)?tab(le)?\.?\s*\d", re.IGNORECASE)
HYPHEN_RE = re.compile(r"[a-z]-$")


def _join_lines(lines: list[str]) -> str:
    """Reflow a block's PDF line-wraps into one flowing string, undoing
    end-of-line hyphenation (the same fix kreuzberg's Markdown mode does,
    now happening on our own controlled per-block text)."""
    if not lines:
        return ""
    result = lines[0]
    for line in lines[1:]:
        # Only de-hyphenate into a lowercase continuation: "under-" + "stood"
        # is a soft line-wrap artifact, but "factor-" + "6" (as in "ATF6") is
        # a real compound term whose hyphen must survive — ambiguous either
        # way from the hyphen alone, but English prose overwhelmingly favors
        # the lowercase-continuation reading for genuine word-wraps.
        if HYPHEN_RE.search(result) and line[:1].islower():
            result = result[:-1] + line
        else:
            result = result + " " + line
    return result.strip()


@dataclass
class Block:
    page: int
    bbox: tuple
    font: str
    size: float
    bold: bool
    n_lines: int
    n_chars: int
    text: str
    type: str = "unclassified"
    section: str | None = None

    @property
    def x0(self):
        return self.bbox[0]

    @property
    def y0(self):
        return self.bbox[1]

    @property
    def x1(self):
        return self.bbox[2]

    @property
    def y1(self):
        return self.bbox[3]

    @property
    def width(self):
        return self.x1 - self.x0


@dataclass
class PageStats:
    width: float
    height: float
    content_x0: float
    content_y0: float
    content_x1: float
    content_y1: float
    column_mid: float


@dataclass
class DocStats:
    body_size: float
    body_font: str
    second_size: float
    second_font: str
    line_height: float
    pages: dict = field(default_factory=dict)  # page_index -> PageStats


def load_blocks(pdf_path: str) -> list[Block]:
    doc = fitz.open(pdf_path)
    blocks = []
    for page_index, page in enumerate(doc):
        raw = page.get_text("dict")
        for b in raw["blocks"]:
            if b.get("type") != 0:
                continue
            sizes, fonts, line_texts = [], [], []
            bold_chars = total_chars = 0
            for line in b["lines"]:
                line_parts = []
                prev_x1 = None
                for span in line["spans"]:
                    n = len(span["text"])
                    if n == 0:
                        continue
                    sizes.extend([round(span["size"], 1)] * n)
                    fonts.extend([span["font"]] * n)
                    if span["flags"] & BOLD_FLAG or "bold" in span["font"].lower():
                        bold_chars += n
                    total_chars += n
                    # Some PDFs space words via glyph positioning rather than a
                    # literal space character; a visible gap between spans with
                    # no space on either side needs one inserted, or adjacent
                    # words glue together (e.g. "fourcis-acting").
                    span_x0 = span["bbox"][0]
                    if (prev_x1 is not None and span_x0 - prev_x1 > 1.0
                            and line_parts and not line_parts[-1].endswith((" ", "-"))
                            and not span["text"].startswith(" ")):
                        line_parts.append(" ")
                    line_parts.append(span["text"])
                    prev_x1 = span["bbox"][2]
                line_text = "".join(line_parts).strip()
                if line_text:
                    line_texts.append(line_text)
            text = _join_lines(line_texts)
            if not text or total_chars == 0:
                continue
            blocks.append(Block(
                page=page_index,
                bbox=tuple(b["bbox"]),
                font=statistics.mode(fonts),
                size=statistics.mode(sizes),
                bold=(bold_chars / total_chars) > 0.5,
                n_lines=len(b["lines"]),
                n_chars=total_chars,
                text=text,
            ))
    doc.close()
    return blocks


def compute_doc_stats(blocks: list[Block], n_pages: int) -> DocStats:
    # Char-weighted (font, size) frequency, skipping tiny/noise blocks.
    freq = Counter()
    for b in blocks:
        if b.n_chars >= 30:
            freq[(b.font, b.size)] += b.n_chars
    ranked = freq.most_common()
    (body_font, body_size), body_n = ranked[0]
    (second_font, second_size), second_n = ranked[1] if len(ranked) > 1 else ranked[0]

    # LA-PDFText's reference-skew guard: if the modal font/size is also
    # dominant on the last quartile of pages and not overwhelmingly more
    # common than the runner-up, a long references section is skewing the
    # global mode — fall back to the second-most-popular as "real" body text.
    tail_start = max(0, int(n_pages * 0.75))
    tail_freq = Counter()
    for b in blocks:
        if b.page >= tail_start and b.n_chars >= 30:
            tail_freq[(b.font, b.size)] += b.n_chars
    tail_dominant = tail_freq.most_common(1)
    if (tail_dominant and tail_dominant[0][0] == (body_font, body_size)
            and second_n and body_n / second_n < 7):
        (body_font, body_size), (second_font, second_size) = (
            (second_font, second_size), (body_font, body_size))

    line_height = body_size * 1.2

    pages = {}
    for p in range(n_pages):
        page_blocks = [b for b in blocks if b.page == p]
        if not page_blocks:
            continue
        # Rotated marginal watermarks ("Author Manuscript" sidebars etc.) are
        # extremely tall/narrow and, being outliers, skew a naive min/max
        # bounding box far past the real text margin — exclude them from the
        # frame calculation (they still exist as blocks; just not as anchors).
        frame_blocks = [b for b in page_blocks if b.width > 0.15 * (b.y1 - b.y0) or b.width > 20]
        if not frame_blocks:
            frame_blocks = page_blocks
        x0 = min(b.x0 for b in frame_blocks)
        y0 = min(b.y0 for b in frame_blocks)
        x1 = max(b.x1 for b in frame_blocks)
        y1 = max(b.y1 for b in frame_blocks)
        pages[p] = PageStats(
            width=0, height=0,  # filled by caller if needed
            content_x0=x0, content_y0=y0, content_x1=x1, content_y1=y1,
            column_mid=(x0 + x1) / 2,
        )
    return DocStats(body_size=body_size, body_font=body_font,
                     second_size=second_size, second_font=second_font,
                     line_height=line_height, pages=pages)


def _section_label(text: str) -> str | None:
    head = text.strip().splitlines()[0].strip() if text.strip() else ""
    for label, pattern in SECTION_PATTERNS:
        if re.match(pattern, head, re.IGNORECASE):
            return label
    return None


def _aligned_with_column(b: Block, stats: DocStats, tol: float) -> bool:
    ps = stats.pages.get(b.page)
    if ps is None:
        return True
    left_ok = abs(b.x0 - ps.content_x0) < tol
    right_ok = abs(b.x1 - ps.content_x1) < tol
    mid_left_ok = abs(b.x0 - ps.column_mid) < tol
    return left_ok or right_ok or mid_left_ok


def classify_blocks(blocks: list[Block], stats: DocStats, n_pages: int) -> None:
    ordered = sorted(blocks, key=lambda b: (b.page, b.y0, b.x0))
    current_section = None
    last_typed_block = None

    for b in ordered:
        ps = stats.pages.get(b.page)
        tol = stats.line_height

        is_top = ps is not None and abs(b.y0 - ps.content_y0) < tol
        is_bottom = ps is not None and abs(b.y1 - ps.content_y1) < tol
        centered = ps is not None and abs(
            ((b.x0 + b.x1) / 2) - ((ps.content_x0 + ps.content_x1) / 2)
        ) < 0.15 * (ps.content_x1 - ps.content_x0)

        if (b.n_lines <= 2 and (is_top or is_bottom) and b.n_chars < 150
                and b.size < stats.body_size - 0.4):
            b.type = "header" if is_top else "footer"

        elif b.page == 0 and b.size >= stats.body_size + 3 and b.n_lines <= 6 and centered:
            b.type = "title"

        elif (b.size >= stats.body_size + 1 or b.bold) and b.n_lines <= 3 and b.n_chars < 200 \
                and _aligned_with_column(b, stats, tol * 3):
            b.type = "heading"
            label = _section_label(b.text)
            current_section = label or f"section_p{b.page}_{int(b.y0)}"
            b.section = current_section

        elif FIGURE_RE.match(b.text.strip()):
            b.type = "figure_legend"
            b.section = current_section

        elif (last_typed_block is not None and last_typed_block.type == "figure_legend"
                and abs(b.size - last_typed_block.size) < 0.6 and b.n_chars > 20):
            b.type = "figure_legend"
            b.section = current_section

        elif TABLE_RE.match(b.text.strip()):
            b.type = "table_caption"
            b.section = current_section

        elif (last_typed_block is not None and last_typed_block.type == "table_caption"
                and abs(b.size - last_typed_block.size) < 0.6 and b.n_chars > 20):
            b.type = "table_caption"
            b.section = current_section

        elif b.size <= stats.body_size - 1.5 and b.page >= n_pages * 0.6 and b.n_chars > 10:
            b.type = "back_matter"
            b.section = current_section

        elif (abs(b.size - stats.body_size) < 0.5 or abs(b.size - stats.second_size) < 0.5
                # Safety net: a long, multi-line, non-bold block is prose by
                # shape regardless of exact font size — journals with richer
                # typographic hierarchies (e.g. a distinctly-sized abstract
                # paragraph) can miss the two discrete body/second sizes.
                or (b.n_chars > 80 and b.n_lines >= 2 and not b.bold)):
            b.type = "body"
            b.section = current_section
        else:
            b.type = "unclassified"

        last_typed_block = b


def assemble_reading_order(blocks: list[Block], stats: DocStats) -> list[Block]:
    ordered = []
    by_page = {}
    for b in blocks:
        if b.type in ("header", "footer"):
            continue
        by_page.setdefault(b.page, []).append(b)

    for page in sorted(by_page):
        page_blocks = by_page[page]
        ps = stats.pages.get(page)
        mid = ps.column_mid if ps else 0

        def bucket(b):
            if b.width > 0.6 * (ps.content_x1 - ps.content_x0 if ps else b.width):
                return 0  # midline / full-width
            return 1 if b.x0 < mid else 2  # left column, right column

        page_blocks.sort(key=lambda b: (bucket(b), b.y0, b.x0))
        ordered.extend(page_blocks)

    # Pull figure/table captions out of the body flow and collect them into
    # their own section, in the same relative order they appeared in the
    # document, positioned right before the first back-matter block
    # (references, acknowledgements, etc.). Only the floating blocks move —
    # everything else keeps its original physical-order relationship, so a
    # section heading (type "heading") never gets separated from its own
    # content (type "back_matter" for References/Affiliations) the way a
    # global type-based partition would.
    FLOATING_TYPES = ("figure_legend", "table_caption")
    non_floating = [b for b in ordered if b.type not in FLOATING_TYPES]
    floating = [b for b in ordered if b.type in FLOATING_TYPES]
    insert_at = next((i for i, b in enumerate(non_floating) if b.type == "back_matter"),
                      len(non_floating))
    return non_floating[:insert_at] + floating + non_floating[insert_at:]


def render_markdown(blocks: list[Block]) -> str:
    out = []
    seen_floating = False
    for b in blocks:
        text = b.text.replace("\n", " ").strip()
        if b.type in ("figure_legend", "table_caption") and not seen_floating:
            out.append("## Figures")
            seen_floating = True
        if b.type == "title":
            out.append(f"# {text}")
        elif b.type == "heading":
            out.append(f"## {text}")
        elif b.type == "figure_legend":
            out.append(f"> [FIGURE] {text}")
        elif b.type == "table_caption":
            out.append(f"> [TABLE] {text}")
        else:
            out.append(text)
    return "\n\n".join(out)


def main():
    pdf_path = sys.argv[1]
    doc = fitz.open(pdf_path)
    n_pages = doc.page_count
    doc.close()

    blocks = load_blocks(pdf_path)
    stats = compute_doc_stats(blocks, n_pages)
    classify_blocks(blocks, stats, n_pages)

    print(f"body_font=({stats.body_font!r}, {stats.body_size}) "
          f"second=({stats.second_font!r}, {stats.second_size}) pages={n_pages}")
    print(Counter(b.type for b in blocks))
    print()

    for label in ["title", "heading", "header", "footer", "figure_legend", "table_caption", "back_matter"]:
        items = [b for b in blocks if b.type == label]
        print(f"--- {label} ({len(items)}) ---")
        for b in items[:15]:
            snippet = b.text[:70].replace("\n", " / ")
            sec = f" sec={b.section}" if b.section else ""
            print(f"  p{b.page+1:>2} size={b.size} bold={b.bold}{sec} {snippet!r}")
        print()

    ordered = assemble_reading_order(blocks, stats)
    md = render_markdown(ordered)
    out_path = "parsed_output.md"
    with open(out_path, "w") as f:
        f.write(md)
    print(f"Wrote {len(md):,} chars of reading-order Markdown to {out_path}")


if __name__ == "__main__":
    main()
