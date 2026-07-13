#!/usr/bin/env python3
"""Float (figure/table) region extraction for KEfED curation.

A "float" is a figure or table displayed out of the text flow. The legend/Methods
text gives the experiment's *structure* (the KEfED template); the float IMAGE gives
the *instance* — its data-signature dimensions (panels/axes/series) and values. So
we render each float to an image the curation agent can read, and pair it with its
numbered caption.

Detection is caption-anchored + negative-space, NOT raster-only, so it generalizes:
  - captions (Fig N / Table N) are found via pdf_layout_parser's block classifier;
  - candidate float regions are page areas with LOW body-text coverage that carry
    graphical content — embedded raster images OR native vector drawings OR table
    grid-lines — so vector figures and ruled tables are caught, not just rasters;
  - regions are column-aware and there may be several per page;
  - each caption claims the adjacent region in reading order (same page above/below,
    or the facing page for a full-page float);
  - anything unpaired is FLAGGED, never silently dropped or mis-paired.

Rendering is always a CLIP-render (page.get_pixmap(clip=...)), never extract_image:
compositing raster+vector+text preserves the separately-positioned panel letters
(a/b/c) and axis labels that a bare image XObject would omit.
"""
import contextlib
import io
import re
import sys
from dataclasses import dataclass, field

import fitz  # PyMuPDF

import pdf_layout_parser as plp


def _find_tables(page):
    """PyMuPDF's find_tables prints a buffered 'use pymupdf_layout' hint to
    sys.stdout, which would corrupt a caller parsing our JSON — redirect it away."""
    with contextlib.redirect_stdout(io.StringIO()):
        try:
            return list(page.find_tables().tables)
        except Exception:
            return []

_NUM = re.compile(r"\d+")
# minimum fraction of page area for a graphical item to count as float content
MIN_IMG_FRAC = 0.02      # embedded raster block
MIN_VEC_FRAC = 0.004     # a single vector path's bbox (dots/rules are smaller)
MAX_ITEM_FRAC = 0.90     # exclude full-page borders/backgrounds
MIN_REGION_FRAC = 0.06   # an uncaptioned region must be at least this big to keep
TEXT_COV_MAX = 0.35      # "negative space": body-text coverage below this = float-like


def _area(r):
    return max(0.0, (r[2] - r[0])) * max(0.0, (r[3] - r[1]))


def _union(a, b):
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def _inter(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    return ix * iy


def _caption_number(text: str) -> str:
    m = _NUM.search(text or "")
    return m.group(0) if m else "?"


def _clean_caption(text: str) -> str:
    """Drop a leading stray glyph/ligature artifact (e.g. '\\x83') some PDFs prepend
    before 'Fig. N', matching what pdf_layout_parser's markdown render strips."""
    return re.sub(r"^\W+", "", (text or "")).strip()


@dataclass
class Region:
    page: int
    rect: tuple
    column: int          # 0 full-width, 1 left, 2 right
    has_image: bool = False
    has_vector: bool = False
    is_table: bool = False
    text_cov: float = 0.0
    area_frac: float = 0.0


@dataclass
class Float:
    kind: str            # "figure" | "table"
    number: str
    caption_page: int
    caption_text: str
    region: Region | None = None
    unpaired: bool = False
    reason: str = ""
    table_rows: list | None = None

    @property
    def label(self):
        return f"{'Figure' if self.kind == 'figure' else 'Table'} {self.number}"


def _column_of(rect, ps) -> int:
    if ps is None:
        return 0
    mid = ps.column_mid
    x0, _, x1, _ = rect
    if x0 < mid - 5 and x1 > mid + 5:
        return 0
    return 1 if (x0 + x1) / 2 < mid else 2


def _vgap(a, b) -> float:
    """Vertical gap between two rects if they x-overlap; else a large sentinel."""
    if min(a[2], b[2]) - max(a[0], b[0]) <= 0:
        return 1e9
    return max(0.0, max(a[1], b[1]) - min(a[3], b[3]))


def _body_cov(region_rect, body_blocks) -> float:
    ra = _area(region_rect)
    if ra <= 0:
        return 0.0
    covered = sum(_inter(region_rect, b.bbox) for b in body_blocks)
    return min(1.0, covered / ra)


def find_float_regions(doc, stats, blocks) -> list[Region]:
    """Per page, cluster graphical content (images + vector + table grid) into
    column-aware regions, keep those that read as negative space."""
    body_by_page: dict[int, list] = {}
    for b in blocks:
        if b.type in ("body", "heading", "back_matter"):
            body_by_page.setdefault(b.page, []).append(b)

    regions: list[Region] = []
    for pno in range(doc.page_count):
        page = doc[pno]
        ps = stats.pages.get(pno)
        A = page.rect.width * page.rect.height
        gap = stats.line_height * 4

        items = []  # (rect, has_image, has_vector, is_table)
        raw = page.get_text("dict")
        for b in raw["blocks"]:
            if b.get("type") == 1 and _area(b["bbox"]) > MIN_IMG_FRAC * A:
                items.append((tuple(b["bbox"]), True, False, False))
        for dw in page.get_drawings():
            r = dw.get("rect")
            if r is not None and MIN_VEC_FRAC * A < _area(tuple(r)) < MAX_ITEM_FRAC * A:
                items.append((tuple(r), False, True, False))
        # NB: find_tables is intentionally NOT used for region *detection* — it
        # over-fires on grid-like structure inside vector figures (false "tables").
        # A ruled table still surfaces here via its grid-lines (vector items); a
        # table is identified by its Table-N caption, and find_tables is used only
        # to pull structured rows from an already caption-anchored table region.
        if not items:
            continue

        # column-aware vertical-proximity merge
        merged: list[Region] = []
        for rect, im, vec, tab in sorted(items, key=lambda t: (_column_of(t[0], ps), t[0][1])):
            col = _column_of(rect, ps)
            for reg in merged:
                if reg.column == col and _vgap(reg.rect, rect) < gap:
                    reg.rect = _union(reg.rect, rect)
                    reg.has_image |= im
                    reg.has_vector |= vec
                    reg.is_table |= tab
                    break
            else:
                merged.append(Region(page=pno, rect=rect, column=col,
                                      has_image=im, has_vector=vec, is_table=tab))

        for reg in merged:
            reg.text_cov = _body_cov(reg.rect, body_by_page.get(pno, []))
            reg.area_frac = _area(reg.rect) / A if A else 0.0
            regions.append(reg)
    return regions


def _seed_table_regions(doc, stats, blocks, regions):
    """Borderless/ruled tables carry little graphical content, so `find_float_regions`
    (raster/vector negative-space) misses them entirely — the Table-N caption then
    steals an adjacent FIGURE's region, cascading the pairing and dropping a real figure.
    Seed an explicit is_table Region from PyMuPDF `find_tables` on each page that carries
    a `table_caption` anchor (and its neighbours), so the table gets its own region and
    figure detection is left untouched (find_tables is scoped to caption pages only)."""
    A_by_page = {}
    cap_pages = {b.page for b in blocks if b.type == "table_caption"}
    seed_pages = set()
    for p in cap_pages:
        seed_pages.update((p - 1, p, p + 1))
    for pno in sorted(pp for pp in seed_pages if 0 <= pp < doc.page_count):
        page = doc[pno]
        ps = stats.pages.get(pno)
        A = page.rect.width * page.rect.height
        for t in _find_tables(page):
            rect = tuple(t.bbox)
            if _area(rect) <= 0:
                continue
            # skip if an existing region already covers this table area
            if any(r.page == pno and _inter(r.rect, rect) > 0.5 * _area(rect) for r in regions):
                continue
            regions.append(Region(page=pno, rect=rect, column=_column_of(rect, ps),
                                   is_table=True, area_frac=(_area(rect) / A if A else 0.0)))


def _caption_anchors(blocks):
    out = []
    for b in blocks:
        if b.type == "figure_legend" and plp.FIGURE_RE.match(b.text.strip()):
            out.append(("figure", b))
        elif b.type == "table_caption" and plp.TABLE_RE.match(b.text.strip()):
            out.append(("table", b))
    return out


def associate(regions, blocks, stats) -> list[Float]:
    """Pair each numbered caption with the adjacent float region (same page
    above/below, or the facing page for a full-page float). Flag the rest."""
    floats: list[Float] = []
    used = set()
    for kind, cap in _caption_anchors(blocks):
        cap_ps = stats.pages.get(cap.page)
        cap_col = _column_of(cap.bbox, cap_ps)
        best, best_score = None, None
        for i, reg in enumerate(regions):
            if i in used or reg.page not in (cap.page, cap.page - 1, cap.page + 1):
                continue
            # a table caption should prefer a table region and vice-versa
            kind_bonus = 0 if (kind == "table") == reg.is_table else 1
            page_pen = abs(reg.page - cap.page)
            col_pen = 0 if (reg.column == 0 or cap_col == 0 or reg.column == cap_col) else 1
            if reg.page == cap.page:
                # region above the caption, or below it
                ygap = min(abs(cap.bbox[1] - reg.rect[3]), abs(reg.rect[1] - cap.bbox[3]))
            else:
                ygap = 0.0  # cross-page: adjacency is by page, not y
            score = (kind_bonus, page_pen, col_pen, ygap)
            if best_score is None or score < best_score:
                best, best_score, best_i = reg, score, i
        if best is None:
            floats.append(Float(kind=kind, number=_caption_number(cap.text),
                                 caption_page=cap.page, caption_text=_clean_caption(cap.text)[:200],
                                 unpaired=True, reason="no adjacent graphical region within page +/-1"))
        else:
            used.add(best_i)
            floats.append(Float(kind=kind, number=_caption_number(cap.text),
                                 caption_page=cap.page, caption_text=_clean_caption(cap.text)[:200],
                                 region=best))
    # uncaptioned regions that look like real floats (big + negative space) -> flag.
    # Suppress noise: too-small regions (mastheads/logos) and regions that overlap an
    # already-paired float (e.g. find_tables firing on a heatmap grid inside a figure).
    paired_rects = [(f.region.page, f.region.rect) for f in floats if f.region]
    for i, reg in enumerate(regions):
        if i in used:
            continue
        if reg.area_frac < MIN_REGION_FRAC:
            continue
        if not (reg.has_image or reg.is_table or reg.has_vector) or reg.text_cov > TEXT_COV_MAX:
            continue
        smaller = _area(reg.rect)
        if any(pg == reg.page and _inter(pr, reg.rect) > 0.5 * smaller for pg, pr in paired_rects):
            continue
        floats.append(Float(kind="table" if reg.is_table else "figure", number="?",
                             caption_page=reg.page, caption_text="",
                             region=reg, unpaired=True,
                             reason="graphical region with no matched caption"))
    return floats


def render_region(page, rect, zoom=3.0, pad=4) -> bytes:
    r = (fitz.Rect(rect) + (-pad, -pad, pad, pad)) & page.rect
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=r)
    return pix.tobytes("png")


def extract_table_rows(page, rect):
    best, best_ov = None, 0.0
    for t in _find_tables(page):
        ov = _inter(tuple(t.bbox), rect)
        if ov > best_ov:
            best, best_ov = t, ov
    try:
        return best.extract() if best else None
    except Exception:
        return None


def extract_floats(pdf_path: str):
    doc = fitz.open(pdf_path)
    n = doc.page_count
    blocks = plp.load_blocks(pdf_path)
    stats = plp.compute_doc_stats(blocks, n)
    plp.classify_blocks(blocks, stats, n)
    regions = find_float_regions(doc, stats, blocks)
    _seed_table_regions(doc, stats, blocks, regions)
    floats = associate(regions, blocks, stats)
    # fill table rows for paired tables
    for f in floats:
        if f.region and f.kind == "table":
            f.table_rows = extract_table_rows(doc[f.region.page], f.region.rect)
    return doc, floats


def main():
    pdf_path = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "."
    doc, floats = extract_floats(pdf_path)
    paired = [f for f in floats if not f.unpaired]
    unpaired = [f for f in floats if f.unpaired]
    print(f"{len(paired)} paired float(s), {len(unpaired)} flagged")
    for f in sorted(paired, key=lambda x: (x.kind, x.caption_page)):
        r = f.region
        png = render_region(doc[r.page], r.rect)
        fn = f"{out_dir}/float_{f.kind}_{f.number}.png"
        with open(fn, "wb") as fh:
            fh.write(png)
        rows = f" rows={len(f.table_rows)}" if f.table_rows else ""
        print(f"  {f.label:11} img_page={r.page+1:>2} legend_page={f.caption_page+1:>2} "
              f"col={r.column} img={r.has_image} vec={r.has_vector} tbl={r.is_table} "
              f"text_cov={r.text_cov:.2f}{rows}  wrote {fn}")
    for f in unpaired:
        loc = f"p{f.region.page+1}" if f.region else f"caption p{f.caption_page+1}"
        print(f"  [FLAG] {f.label} ({loc}): {f.reason}")
    doc.close()


if __name__ == "__main__":
    main()
