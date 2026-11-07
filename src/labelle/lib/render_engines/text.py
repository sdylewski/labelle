from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageFont

from labelle.lib.constants import Direction
from labelle.lib.render_engines.math_text import (
    draw_box,
    layout_line,
    text_needs_fallback,
)
from labelle.lib.render_engines.render_context import RenderContext
from labelle.lib.render_engines.render_engine import RenderEngine
from labelle.lib.utils import draw_image


class TextRenderEngine(RenderEngine):
    def __init__(
        self,
        text_lines: str | list[str],
        font_file_name: Path | str,
        frame_width_px: int = 0,
        font_size_ratio: float = 0.9,
        align: Direction = Direction.CENTER,
        math: bool = False,
    ):
        if isinstance(text_lines, str):
            text_lines = [text_lines]

        if len(text_lines) == 0:
            text_lines = [" "]

        self.text_lines = text_lines
        self.font_file_name = font_file_name
        self.frame_width_px = frame_width_px
        self.font_size_ratio = font_size_ratio
        self.align = align
        self.math = math

        super().__init__()

    def render(self, context: RenderContext) -> Image.Image:
        height_px = context.height_px
        line_height = float(height_px) / len(self.text_lines)
        font_size_px = round(line_height * self.font_size_ratio)

        font_offset_px = int((line_height - font_size_px) / 2)
        if self.frame_width_px:
            frame_width_px = self.frame_width_px or min(
                self.frame_width_px, font_offset_px, 3
            )
        else:
            frame_width_px = self.frame_width_px

        font_path = str(self.font_file_name)
        if self.math or any(
            text_needs_fallback(line, font_path) for line in self.text_lines
        ):
            return self._render_rich(
                height_px, line_height, font_size_px, font_offset_px, frame_width_px
            )

        font = ImageFont.truetype(font_path, font_size_px)
        boxes = (font.getbbox(line) for line in self.text_lines)
        line_widths = (right - left for left, _top, right, _bottom in boxes)
        label_width_px = max(line_widths) + (font_offset_px * 2)
        bitmap = Image.new("1", (label_width_px, height_px))
        with draw_image(bitmap) as draw:
            # draw frame into empty image
            if frame_width_px:
                draw.rectangle(((0, 4), (label_width_px - 1, height_px - 4)), fill=1)
                draw.rectangle(
                    (
                        (frame_width_px, 4 + frame_width_px),
                        (
                            label_width_px - (frame_width_px + 1),
                            height_px - (frame_width_px + 4),
                        ),
                    ),
                    fill=0,
                )

            # write the text into the empty image
            multiline_text = "\n".join(self.text_lines)
            draw.multiline_text(
                (label_width_px / 2, height_px / 2),
                multiline_text,
                align=self.align.value,
                anchor="mm",
                font=font,
                fill=1,
            )
        return bitmap

    def _render_rich(
        self,
        height_px: int,
        line_height: float,
        font_size_px: int,
        font_offset_px: int,
        frame_width_px: int,
    ) -> Image.Image:
        """Render with symbol fallback fonts and (optionally) math markup."""
        font_path = str(self.font_file_name)
        line_boxes = []
        for line in self.text_lines:
            box = layout_line(line, font_path, font_size_px, self.math)
            # Tall math (fractions, nested powers) is shrunk to fit its line.
            if self.math and box.height > line_height and box.height > 0:
                scaled = max(1, int(font_size_px * line_height / box.height))
                box = layout_line(line, font_path, scaled, self.math)
            line_boxes.append(box)

        content_width = max((b.width for b in line_boxes), default=0)
        label_width_px = max(1, round(content_width) + font_offset_px * 2)
        bitmap = Image.new("1", (label_width_px, height_px))
        with draw_image(bitmap) as draw:
            if frame_width_px:
                draw.rectangle(((0, 4), (label_width_px - 1, height_px - 4)), fill=1)
                draw.rectangle(
                    (
                        (frame_width_px, 4 + frame_width_px),
                        (
                            label_width_px - (frame_width_px + 1),
                            height_px - (frame_width_px + 4),
                        ),
                    ),
                    fill=0,
                )
            for i, box in enumerate(line_boxes):
                if self.align == Direction.LEFT:
                    x = font_offset_px
                elif self.align == Direction.RIGHT:
                    x = font_offset_px + content_width - box.width
                else:
                    x = font_offset_px + (content_width - box.width) / 2
                slot_top = i * line_height
                baseline = slot_top + (line_height - box.height) / 2 + box.ascent
                draw_box(draw, box, x, baseline)
        return bitmap
