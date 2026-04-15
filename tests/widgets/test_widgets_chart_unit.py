from PIL import Image, ImageDraw

from gopro_overlay.framemeta import View
from gopro_overlay.widgets.chart import SimpleChart


def draw_chart(chart, w=500, h=200):
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    chart.draw(img, draw)
    return img


def linear_view(n=256, lo=0.0, hi=1.0, version=1):
    step = (hi - lo) / max(n - 1, 1)
    return View(data=[lo + i * step for i in range(n)], version=version)


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
