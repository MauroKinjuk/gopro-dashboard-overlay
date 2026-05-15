from functools import cached_property

from PIL import ImageDraw, Image

from .widgets import Widget


class GradientBar(Widget):

    def __init__(self, size, reading, min_value=0, max_value=1000, z1_value=120, z2_value=150, z3_value=180, z4_value=200, cr=5,
                 fill=(255, 255, 255, 0),
                 outline=(255, 255, 255),
                 outline_width=3,
                 z0_col=(255, 255, 255),
                 z1_col=(67, 235, 52),
                 z2_col=(240, 232, 19),
                 z3_col=(207, 19, 2),
                 z4_col=(139, 0, 0),
                 divider=(255, 255, 255),
                 mode="gradient",
                 indicator=(255, 255, 255),
                 indicator_width=3,
                 inactive_alpha=1.0,
                 zone_widths=None,
                 ):
        self.reading = reading
        self.size = size
        self.corner_radius = cr
        self.outline = outline
        self.fill = fill
        self.divider = divider
        self.mode = mode
        self.indicator = indicator
        self.indicator_width = indicator_width
        self.inactive_alpha = inactive_alpha
        self.zone_widths = zone_widths

        self.line_width = outline_width
        self.min_value = min_value
        self.max_value = max_value
        self.z1_value = z1_value
        self.z2_value = z2_value
        self.z3_value = z3_value
        self.z4_value = z4_value
        self.z0_col = z0_col
        self.z1_col = z1_col
        self.z2_col = z2_col
        self.z3_col = z3_col
        self.z4_col = z4_col

    def x_coord(self, value):
        value = max(min(value, self.max_value), self.min_value)
        scale = self.scale
        shifted = value - self.min_value
        return shifted * scale

    @cached_property
    def scale(self):
        range = self.max_value - self.min_value
        scale = (self.size.x - (self.line_width + 2)) / range  # px/unit
        return scale

    def value(self, x_coord):
        scale = self.scale
        shifted = x_coord / scale
        return shifted + self.min_value

    def _zone_ranges(self):
        return [
            (self.min_value, self.z1_value),
            (self.z1_value, self.z2_value),
            (self.z2_value, self.z3_value),
            (self.z3_value, self.z4_value),
            (self.z4_value, self.max_value),
        ]

    def _visual_zone_widths(self):
        if not self.zone_widths:
            ranges = self._zone_ranges()
            total = sum(z_max - z_min for z_min, z_max in ranges)
            return [((z_max - z_min) / total) * (self.size.x - (self.line_width + 2)) for z_min, z_max in ranges]
        weights = list(self.zone_widths)
        total = sum(weights)
        bar_width = self.size.x - (self.line_width + 2)
        return [(w / total) * bar_width for w in weights]

    def _visual_x_for_value(self, value):
        if not self.zone_widths:
            return self.x_coord(value)
        ranges = self._zone_ranges()
        widths = self._visual_zone_widths()
        value = max(min(value, self.max_value), self.min_value)
        for i, (z_min, z_max) in enumerate(ranges):
            if value <= z_max or i == len(ranges) - 1:
                offset = sum(widths[:i])
                local = (value - z_min) / (z_max - z_min) if z_max != z_min else 0
                return offset + local * widths[i] + self.line_width
        return self.line_width

    def _visual_zone_coords(self):
        ranges = self._zone_ranges()
        widths = self._visual_zone_widths()
        coords = []
        x = self.line_width
        for i, (z_min, z_max) in enumerate(ranges):
            x1 = x
            x2 = x + widths[i]
            coords.append((x1, x2))
            x = x2
        return coords

    # TODO: REFACTOR
    def get_color(self, x_coord):
        value = self.value(x_coord)
        if value < self.z1_value:
            range = self.x_coord(self.z1_value) - self.x_coord(self.min_value)
            i = x_coord - self.x_coord(self.min_value)
            gradient_step = [(t - f) / range for f, t in zip(self.z0_col, self.z1_col)]
            return [round(f + gs * i) for f, gs in zip(self.z0_col, gradient_step)]
        elif value < self.z2_value:
            range = self.x_coord(self.z2_value) - self.x_coord(self.z1_value)
            i = x_coord - self.x_coord(self.z1_value)
            gradient_step = [(t - f) / range for f, t in zip(self.z1_col, self.z2_col)]
            return [round(f + gs * i) for f, gs in zip(self.z1_col, gradient_step)]
        elif value < self.z3_value:
            range = self.x_coord(self.z3_value) - self.x_coord(self.z2_value)
            i = x_coord - self.x_coord(self.z2_value)
            gradient_step = [(t - f) / range for f, t in zip(self.z2_col, self.z3_col)]
            return [round(f + gs * i) for f, gs in zip(self.z2_col, gradient_step)]
        elif value < self.z4_value:
            range = self.x_coord(self.z4_value) - self.x_coord(self.z3_value)
            i = x_coord - self.x_coord(self.z3_value)
            gradient_step = [(t - f) / range for f, t in zip(self.z3_col, self.z4_col)]
            return [round(f + gs * i) for f, gs in zip(self.z3_col, gradient_step)]
        else:
            return self.z4_col

    def draw(self, image: Image, draw: ImageDraw):
        current = self.reading()

        # Fondo sólido opaco para toda la barra (evita transparencia sobre video)
        bg_col = self.fill
        if bg_col is None or (len(bg_col) == 4 and bg_col[3] == 0):
            bg_col = (100, 100, 100)
        draw.rectangle(
            ((0, 0), (self.size.x - 1, self.size.y - 1)),
            fill=bg_col
        )

        draw.rounded_rectangle(
            ((0, 0), (self.size.x - 1, self.size.y - 1)),
            radius=self.corner_radius,
            fill=None,
            outline=self.outline,
            width=self.line_width,
        )

        def with_alpha(col, alpha):
            if alpha >= 1.0:
                return col
            if len(col) == 3:
                return (*col, int(255 * alpha))
            elif len(col) == 4:
                return (*col[:3], int(col[3] * alpha))
            return col

        if self.mode == "solid":
            zones = [
                (self.min_value, self.z1_value, self.z0_col),
                (self.z1_value, self.z2_value, self.z1_col),
                (self.z2_value, self.z3_value, self.z2_col),
                (self.z3_value, self.z4_value, self.z3_col),
                (self.z4_value, self.max_value, self.z4_col),
            ]
            zone_coords = self._visual_zone_coords()
            current_x = round(self._visual_x_for_value(current))
            # Pintar fondo completo con alpha reducida si aplica
            y1 = 0 if self.line_width == 0 else self.line_width + 1
            y2 = self.size.y - 1 if self.line_width == 0 else self.size.y - self.line_width - 2
            if self.inactive_alpha < 1.0:
                for i, (z_min, z_max, col) in enumerate(zones):
                    x1, x2 = zone_coords[i]
                    x1 = round(max(x1, self.line_width))
                    x2 = round(min(x2, self.size.x - self.line_width - 1))
                    if x2 > x1:
                        draw.rectangle(
                            ((x1, y1), (x2, y2)),
                            fill=with_alpha(col, self.inactive_alpha)
                        )
            # Pintar zonas activas (hasta current) con color opaco
            for i, (z_min, z_max, col) in enumerate(zones):
                x1, x2 = zone_coords[i]
                x2_active = min(x2, current_x)
                x1 = round(max(x1, self.line_width))
                x2_active = round(min(x2_active, self.size.x - self.line_width - 1))
                if x2_active > x1:
                    draw.rectangle(
                        ((x1, y1), (x2_active, y2)),
                        fill=col
                    )
        else:
            draw.line(
                ((self.x_coord(0), 0), (self.x_coord(0), self.size.y)),
                fill=self.divider
            )
            start_x = max(round(self.x_coord(0)) + self.line_width, self.line_width)
            end_x = round(self.x_coord(current))
            for i in range(start_x, end_x):
                draw.line(((i, self.line_width), (i, self.size.y - self.line_width - 1)), tuple(self.get_color(i)), width=1)

        if self.divider:
            for v in (self.z1_value, self.z2_value, self.z3_value, self.z4_value):
                x_div = round(self._visual_x_for_value(v))
                if self.line_width <= x_div <= self.size.x - self.line_width - 1:
                    draw.line(
                        ((x_div, self.line_width), (x_div, self.size.y - self.line_width - 1)),
                        fill=self.divider
                    )

        if self.indicator and self.indicator_width > 0:
            indicator_x = round(self._visual_x_for_value(current))
            if self.line_width <= indicator_x <= self.size.x - self.line_width - 1:
                draw.line(
                    ((indicator_x, self.line_width + 1), (indicator_x, self.size.y - self.line_width - 2)),
                    fill=self.indicator,
                    width=self.indicator_width
                )
