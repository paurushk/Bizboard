"""Draw complex-script text (Devanagari) into a ReportLab canvas as vector outlines.

ReportLab places glyphs one by one in logical order and does no OpenType shaping, so Hindi
vowel signs land on the wrong side of the consonant and conjuncts do not form. HarfBuzz does
the shaping; each shaped glyph's outline is then drawn as a filled path.

Outlines are not text, so on their own the Hindi could not be selected, searched or read by a
screen reader. Each shaped run is therefore wrapped in a marked-content span carrying
``/ActualText`` with the real Unicode string (ISO 32000-1 14.9.4), around an invisible text object
(render mode 3) set in the same font. Viewers that honour ActualText (Acrobat, Chrome's PDF viewer,
pdf.js) return the Hindi from copy, find and assistive tools; ones that ignore it still read the
same Unicode from the invisible text. Nothing is double-printed: the invisible text is never drawn.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import FILL_NON_ZERO

logger = logging.getLogger(__name__)

try:  # the voucher falls back to English when the shaper is not installed
    import uharfbuzz as hb
except Exception:  # pragma: no cover - exercised by the fallback test via monkeypatch
    hb = None


class _OutlinePen:
    """Collects a glyph outline as cubic Bezier commands in font units (fontTools pen protocol)."""

    def __init__(self):
        self.commands: list[tuple] = []
        self._current: tuple[float, float] | None = None

    def moveTo(self, pt):
        self._current = pt
        self.commands.append(("M", pt))

    def lineTo(self, pt):
        self._current = pt
        self.commands.append(("L", pt))

    def curveTo(self, *pts):
        # Cubic: any number of off-curve points is not valid in a glyf table; HarfBuzz gives 3.
        c1, c2, end = pts[-3:]
        self._current = end
        self.commands.append(("C", c1, c2, end))

    def qCurveTo(self, *pts):
        # Quadratic spline with implied on-curve points between consecutive off-curve points.
        *offs, end = pts
        if end is None:
            return
        start = self._current
        for i, ctrl in enumerate(offs):
            nxt = end if i == len(offs) - 1 else ((ctrl[0] + offs[i + 1][0]) / 2, (ctrl[1] + offs[i + 1][1]) / 2)
            c1 = (start[0] + 2 / 3 * (ctrl[0] - start[0]), start[1] + 2 / 3 * (ctrl[1] - start[1]))
            c2 = (nxt[0] + 2 / 3 * (ctrl[0] - nxt[0]), nxt[1] + 2 / 3 * (ctrl[1] - nxt[1]))
            self.commands.append(("C", c1, c2, nxt))
            start = nxt
        self._current = end

    def closePath(self):
        self.commands.append(("Z",))

    endPath = closePath


class ShapedFont:
    """One font file at one weight, with shaping and glyph outlines cached."""

    def __init__(self, path: Path, weight: int | None = None):
        self._path = Path(path)
        self._text_font: str | None = None
        blob = hb.Blob.from_file_path(str(path))
        self._face = hb.Face(blob)
        self._font = hb.Font(self._face)
        if weight is not None:
            try:
                self._font.set_variations({"wght": weight})
            except Exception:  # a static font has no weight axis
                logger.info("shaped_text.no_weight_axis path=%s", path)
        self.upem = self._face.upem
        self._outlines: dict[int, list[tuple]] = {}

    def shape(self, text: str) -> list[tuple[int, float, float, float]]:
        """[(glyph id, x advance, x offset, y offset)] in font units, in visual order."""
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(self._font, buf, {})
        return [
            (info.codepoint, pos.x_advance, pos.x_offset, pos.y_offset)
            for info, pos in zip(buf.glyph_infos, buf.glyph_positions, strict=True)
        ]

    def width(self, text: str, size: float) -> float:
        return sum(adv for _, adv, _, _ in self.shape(text)) * size / self.upem

    def outline(self, glyph: int) -> list[tuple]:
        cached = self._outlines.get(glyph)
        if cached is None:
            pen = _OutlinePen()
            self._font.draw_glyph_with_pen(glyph, pen)
            cached = self._outlines[glyph] = pen.commands
        return cached

    def _invisible_font(self) -> str | None:
        """The name of this font registered with ReportLab for the invisible text layer, or None."""
        if self._text_font is None:
            name = f"Shaped-{self._path.stem}"
            try:
                if name not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont(name, str(self._path)))
                self._text_font = name
            except Exception:  # an unreadable font only costs searchability, never the voucher
                logger.exception("shaped_text.invisible_font_unavailable path=%s", self._path)
                self._text_font = ""
        return self._text_font or None

    def draw(self, canvas, text: str, x: float, y: float, size: float, *, searchable: bool = True) -> None:
        """Fill the shaped text with its baseline at (x, y), in the canvas's current fill colour.

        With ``searchable`` the run also carries its real Unicode text (see the module docstring).
        """
        name = self._invisible_font() if searchable and text.strip() else None
        if name:
            actual = ("﻿" + text).encode("utf-16-be").hex().upper()
            canvas._code.append(f"/Span << /ActualText <{actual}> >> BDC")
            invisible = canvas.beginText(x, y)
            invisible.setTextRenderMode(3)  # neither filled nor stroked: present, never drawn
            invisible.setFont(name, size)
            invisible.textOut(text)
            canvas.drawText(invisible)
        scale = size / self.upem
        pen_x = x
        path = canvas.beginPath()
        for glyph, adv, x_off, y_off in self.shape(text):
            ox = pen_x + x_off * scale
            oy = y + y_off * scale
            for cmd in self.outline(glyph):
                kind = cmd[0]
                if kind == "M":
                    path.moveTo(ox + cmd[1][0] * scale, oy + cmd[1][1] * scale)
                elif kind == "L":
                    path.lineTo(ox + cmd[1][0] * scale, oy + cmd[1][1] * scale)
                elif kind == "C":
                    (x1, y1), (x2, y2), (x3, y3) = cmd[1], cmd[2], cmd[3]
                    path.curveTo(
                        ox + x1 * scale, oy + y1 * scale,
                        ox + x2 * scale, oy + y2 * scale,
                        ox + x3 * scale, oy + y3 * scale,
                    )
                elif kind == "Z":
                    path.close()
            pen_x += adv * scale
        # Glyph contours overlap and rely on non-zero winding; even-odd would punch holes.
        canvas.drawPath(path, stroke=0, fill=1, fillMode=FILL_NON_ZERO)
        if name:
            canvas._code.append("EMC")


@lru_cache(maxsize=8)
def load_font(path: str, weight: int | None = None) -> ShapedFont:
    return ShapedFont(Path(path), weight)


def shaping_available() -> bool:
    return hb is not None
