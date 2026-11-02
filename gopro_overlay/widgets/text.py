from typing import Callable, Any, Tuple

from PIL import Image, ImageDraw

from gopro_overlay.point import Coordinate
from gopro_overlay.widgets.widgets import Widget


class CachingText(Widget):
    def __init__(self, at: Coordinate, value: Callable, font,
                 align="left", direction="ltr",
                 fill=None,
                 stroke=(0, 0, 0),
                 stroke_width=2,
                 ):
        self.at = at
        self.value = value
        self.font = font
        self.anchor = anchors.get(align, align)
        self.direction = direction
        self.fill = fill if fill else (255, 255, 255)
        self.stroke = stroke
        self.stroke_width = stroke_width
        self.cache = {}

    def draw(self, image: Image, draw: ImageDraw):

        text = self.value()

        if text is None:
            raise ValueError("Refusing to draw text with value of 'None'")

        cached = self.cache.get(text, None)

        if cached is None:
            fill = self.fill() if callable(self.fill) else self.fill
            x0, y0, x1, y1 = self.font.getbbox(
                text=text,
                stroke_width=self.stroke_width,
                anchor=self.anchor,
                direction=None if self.direction == "ltr" else self.direction
            )

            if x0 < 0:
                x1 = x1 + abs(x0)
            if y0 < 0:
                y1 = y1 + abs(y0)

            backing_image = Image.new(mode="RGBA", size=(x1, y1))
            backing_draw = ImageDraw.Draw(backing_image)

            backing_draw.text(
                (abs(x0), 0),
                text,
                anchor=self.anchor,
                direction=None if self.direction == "ltr" else self.direction,
                font=self.font,
                fill=fill,
                stroke_width=self.stroke_width,
                stroke_fill=self.stroke
            )
            cached = {
                "at": Coordinate(x0 if x0 < 0 else 0, y0 if y0 < 0 else 0),
                "image": backing_image
            }
            self.cache[text] = cached

        image.alpha_composite(cached["image"], (self.at + cached["at"]).tuple())


class Text(Widget):
    def __init__(self,
                 at: Coordinate,
                 value: Callable[[], str],
                 font: Any, align: str = "left",
                 direction: str = "ltr",
                 fill: Tuple = None,
                 stroke: Tuple = None,
                 stroke_width: int = 2
                 ) -> None:
        self.at = at
        self.value = value
        self.font = font
        self.anchor = anchors.get(align, align)
        self.direction = direction
        self.fill = fill if fill else (255, 255, 255)
        self.stroke = stroke if stroke else (0, 0, 0)
        self.stroke_width = stroke_width

    def draw(self, image: Image, draw: ImageDraw):
        draw.text(
            self.at.tuple(),
            self.value(),
            anchor=self.anchor,
            direction=None if self.direction == "ltr" else self.direction,
            font=self.font,
            fill=self.fill() if callable(self.fill) else self.fill,
            stroke_width=self.stroke_width,
            stroke_fill=(0, 0, 0)
        )


anchors = {
    "left": "la",
    "right": "ra",
    "centre": "ma",
}


class TextWithSuffix(Widget):
    """Text with a suffix (e.g. a unit) drawn immediately after the value,
    in its own font/colour and baseline-aligned. The suffix may be a string
    or a callable returning a string.

    end_anchored=False (default): value is left-anchored at `at`, suffix follows it.
    end_anchored=True: `at` is the RIGHT edge of the group; the suffix is
    right-anchored there and the value is right-anchored just before it."""

    def __init__(self, at: Coordinate, value: Callable, font,
                 suffix, suffix_font, suffix_fill, gap: int = 0,
                 fill=None, stroke=(0, 0, 0), stroke_width=2,
                 end_anchored: bool = False):
        self.at = at
        self.value = value
        self.font = font
        self.suffix = suffix
        self.suffix_font = suffix_font
        self.suffix_fill = suffix_fill
        self.gap = gap
        self.fill = fill if fill else (255, 255, 255)
        self.stroke = stroke
        self.stroke_width = stroke_width
        self.end_anchored = end_anchored

    def draw(self, image: Image, draw: ImageDraw):
        value = self.value()
        if value is None:
            return
        text = str(value)
        suffix = self.suffix() if callable(self.suffix) else self.suffix
        fill = self.fill() if callable(self.fill) else self.fill
        suffix_fill = self.suffix_fill() if callable(self.suffix_fill) else self.suffix_fill

        if self.end_anchored:
            baseline_y = self.at.y + self.font.getmetrics()[0]
            suffix_w = self.suffix_font.getlength(suffix)
            draw.text(
                (self.at.x - suffix_w - self.gap, self.at.y), text, anchor="ra",
                font=self.font, fill=fill,
                stroke_width=self.stroke_width, stroke_fill=self.stroke,
            )
            draw.text(
                (self.at.x, baseline_y - self.suffix_font.getmetrics()[0]), suffix, anchor="ra",
                font=self.suffix_font, fill=suffix_fill,
                stroke_width=self.stroke_width, stroke_fill=self.stroke,
            )
        else:
            draw.text(
                self.at.tuple(), text, anchor="la",
                font=self.font, fill=fill,
                stroke_width=self.stroke_width, stroke_fill=self.stroke,
            )
            baseline_y = self.at.y + self.font.getmetrics()[0]
            suffix_x = self.at.x + self.font.getlength(text) + self.gap
            suffix_y = baseline_y - self.suffix_font.getmetrics()[0]
            draw.text(
                (suffix_x, suffix_y), suffix, anchor="la",
                font=self.suffix_font, fill=suffix_fill,
                stroke_width=self.stroke_width, stroke_fill=self.stroke,
            )
