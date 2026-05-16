import functools

from PIL import Image, ImageDraw

from .compass import Compass
from .widgets import Widget


class CompassArrow(Widget):

    def __init__(self, size, reading, font,
                 arrow=(255, 255, 255),
                 bg=(0, 0, 0, 0),
                 text=(255, 255, 255),
                 outline=(0, 0, 0),
                 arrow_outline=(0, 0, 0),
                 arrow_length=0.9
                 ):
        self.reading = reading
        self.size = size
        self.font = font
        self.arrow = arrow
        self.arrow_outline = arrow_outline
        self.bg = bg
        self.text = text
        self.outline = outline
        self.arrow_length = arrow_length
        self.last_reading = None
        self.image = None

    def _redraw(self, reading):
        size = self.size
        image = Image.new(mode="RGBA", size=(size, size))

        draw = ImageDraw.Draw(image)

        draw.pieslice(
            ((0, 0), (0 + size, 0 + size)),
            0,
            360,
            outline=self.outline,
            fill=self.bg,
            width=2
        )

        radius = size / 2
        centre = size / 2

        locate = functools.partial(Compass.locate, radius, centre, 0)

        draw.text(locate(0, radius * 0.3), "N", font=self.font, anchor="mm", fill=self.text)
        draw.text(locate(90, radius * 0.3), "E", font=self.font, anchor="mm", fill=self.text)
        draw.text(locate(180, radius * 0.3), "S", font=self.font, anchor="mm", fill=self.text)
        draw.text(locate(270, radius * 0.3), "W", font=self.font, anchor="mm", fill=self.text)

        locate = functools.partial(Compass.locate, radius, centre, -reading)

        # arrow_length: 0=center, 1.0=edge (how far from center the tip is)
        tip_d = radius * (1.0 - self.arrow_length)
        # Base stays fixed near center (10% from center)
        base_d = radius * 0.9
        # Width: proportional to arrow length, with a minimum
        width = max(radius * 0.85, radius * (1.0 - self.arrow_length * 0.5))

        draw.polygon(
            [
                locate(0, tip_d),
                locate(-90, width),
                locate(0, base_d),
                locate(90, width),
            ],
            fill=self.arrow,
            outline=self.arrow_outline,
        )

        return image

    def draw(self, image: Image, draw: ImageDraw):
        reading = - int(self.reading())

        if self.image is None or reading != self.last_reading:
            self.last_reading = reading
            self.image = self._redraw(reading)

        image.alpha_composite(self.image, (0, 0))
