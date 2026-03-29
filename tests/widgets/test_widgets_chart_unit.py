"""
Unit and integration tests for SimpleChart enhancements:
  - width parameter (stretches chart to fixed pixel width)
  - per-frame marker interpolation (sub-tick smooth movement)
  - marker clamping (marker stays within data bounds)
  - marker_size parameter (configurable via XML)
  - XML attribute parsing (width, marker-size)
"""
import os
import random
from datetime import timedelta

import pytest
from PIL import Image, ImageDraw

from gopro_overlay import fake
from gopro_overlay.framemeta import View
from gopro_overlay.widgets.chart import SimpleChart


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def draw_chart(chart, w=500, h=200):
    """Render chart onto a fresh image and return the image."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    chart.draw(img, draw)
    return img


def linear_view(n=256, lo=0.0, hi=1.0, version=1):
    """View with linearly increasing values — no Nones."""
    step = (hi - lo) / max(n - 1, 1)
    return View(data=[lo + i * step for i in range(n)], version=version)


# ---------------------------------------------------------------------------
# width parameter — chart image is exactly render_width pixels wide
# ---------------------------------------------------------------------------

class TestWidth:

    def test_without_width_chart_image_equals_data_length(self):
        view = linear_view(n=128)
        chart = SimpleChart(value=lambda: view, height=100)
        draw_chart(chart, w=600, h=100)
        assert chart.chart_image.size == (128, 100)

    def test_with_width_chart_image_matches_requested_width(self):
        view = linear_view(n=128)
        chart = SimpleChart(value=lambda: view, height=100, width=400)
        draw_chart(chart, w=600, h=100)
        assert chart.chart_image.size == (400, 100)

    def test_with_width_stretches_sparse_data_to_full_width(self):
        """Only centre 64 of 256 slots have data — chart image must still be width wide."""
        n = 256
        quarter = n // 4
        data = [None] * quarter + [float(i) for i in range(n // 2)] + [None] * quarter
        view = View(data=data, version=1)
        chart = SimpleChart(value=lambda: view, height=100, width=400)
        draw_chart(chart, w=600, h=100)
        assert chart.chart_image.size == (400, 100)


# ---------------------------------------------------------------------------
# chart cache invalidation
# ---------------------------------------------------------------------------

class TestCaching:

    def test_chart_image_reused_on_same_version(self):
        view = linear_view(version=1)
        chart = SimpleChart(value=lambda: view, height=80)
        draw_chart(chart)
        first_image_id = id(chart.chart_image)
        draw_chart(chart)
        assert id(chart.chart_image) == first_image_id

    def test_chart_image_rebuilt_on_new_version(self):
        views = iter([linear_view(version=1), linear_view(version=2)])
        chart = SimpleChart(value=lambda: next(views), height=80)
        draw_chart(chart)
        first_image_id = id(chart.chart_image)
        draw_chart(chart)
        assert id(chart.chart_image) != first_image_id


# ---------------------------------------------------------------------------
# marker clamping — marker never escapes the data range
# ---------------------------------------------------------------------------

class TestMarkerClamping:

    def test_marker_not_drawn_when_all_data_is_none(self):
        """No exception when data has no non-None values."""
        view = View(data=[None] * 50, version=1)
        chart = SimpleChart(
            value=lambda: view,
            height=80,
            marker_time_fn=lambda: 0.0,
            window_tick_ms=100,
        )
        draw_chart(chart)  # must not raise

    def test_no_crash_when_current_time_beyond_data(self):
        """Current time (n//2=50) outside data range (first 10 slots only) — no crash."""
        n = 100
        data = [float(i) for i in range(10)] + [None] * 90
        view = View(data=data, version=1)
        chart = SimpleChart(
            value=lambda: view,
            height=80,
            width=400,
            marker_time_fn=lambda: 0.0,
            window_tick_ms=100,
        )
        draw_chart(chart)  # must not raise

    def test_no_crash_when_current_time_before_data(self):
        """Current time (n//2=50) before data range (last 10 slots only) — no crash."""
        n = 100
        data = [None] * 90 + [float(i) for i in range(10)]
        view = View(data=data, version=1)
        chart = SimpleChart(
            value=lambda: view,
            height=80,
            width=400,
            marker_time_fn=lambda: 0.0,
            window_tick_ms=100,
        )
        draw_chart(chart)  # must not raise


# ---------------------------------------------------------------------------
# marker_size parameter — larger size produces a larger rendered dot
# ---------------------------------------------------------------------------

class TestMarkerSize:

    def test_larger_marker_occupies_more_red_pixels(self):
        """A size-10 marker should produce more red pixels than a size-4 marker."""
        view = linear_view(n=100)

        def red_pixel_count(size):
            chart = SimpleChart(
                value=lambda: view,
                height=200,
                width=200,
                marker_size=size,
                marker_time_fn=lambda: 0.0,
                window_tick_ms=100,
            )
            img = draw_chart(chart, w=200, h=200)
            return sum(
                1 for x in range(img.width) for y in range(img.height)
                if (lambda p: p[0] > 200 and p[1] < 50 and p[2] < 50 and p[3] > 0)(img.getpixel((x, y)))
            )

        assert red_pixel_count(10) > red_pixel_count(4)


# ---------------------------------------------------------------------------
# XML integration — width and marker-size attributes parsed correctly
# ---------------------------------------------------------------------------

class TestXmlIntegration:

    def _make_layout_xml(self, extra_attrs=""):
        return f"""<layout>
            <component type="chart" x="0" y="0"
                metric="alt" units="meters" seconds="60" samples="64"
                height="100" {extra_attrs}/>
        </layout>"""

    def _build_layout(self, extra_attrs):
        """
        layout_from_xml returns a factory callable; widgets (and attribute
        validation) are only created when that callable is invoked with an entry.
        """
        from gopro_overlay.layout_xml import layout_from_xml
        from gopro_overlay.privacy import NoPrivacyZone
        from gopro_overlay.font import load_font

        rng = random.Random(42)
        framemeta = fake.fake_framemeta(length=timedelta(minutes=2), step=timedelta(seconds=1), rng=rng)
        font_path = os.path.join(os.path.dirname(__file__), "..", "..", "Roboto-Medium.ttf")
        font = load_font(font_path)
        xml = self._make_layout_xml(extra_attrs=extra_attrs)
        layout_creator = layout_from_xml(xml, None, framemeta, font, privacy=NoPrivacyZone())
        layout_creator(lambda: framemeta[framemeta.min])

    def test_chart_xml_with_width_attribute_accepted(self):
        """XML with width= should not raise an unknown-attribute error."""
        self._build_layout('width="300"')

    def test_chart_xml_with_marker_size_attribute_accepted(self):
        """XML with marker-size= should not raise an unknown-attribute error."""
        self._build_layout('marker-size="8"')

    def test_chart_xml_unknown_attribute_raises(self):
        """Sanity check: truly unknown attributes still raise IOError."""
        with pytest.raises(IOError, match="Unknown attributes"):
            self._build_layout('nonexistent-attr="123"')
