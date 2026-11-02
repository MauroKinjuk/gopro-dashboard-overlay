import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional

from PIL import Image, ImageDraw

from gopro_overlay.point import Coordinate
from gopro_overlay.widgets.widgets import Widget


def _ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


def _parse_dt(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


@dataclass
class _Segment:
    id: str
    name: str
    start: datetime
    end: datetime
    distance_m: float
    pr_rank: Optional[int] = None


class SegmentBannerWidget(Widget):
    """Banner animado que avisa cuando se aproxima un segmento de Strava.

    Estados:
      INCOMING: [start - preview_seconds, start)  -> slide + fade in
      GO:       [start, start + go_seconds)       -> flash "¡SEGMENTO!"
      ACTIVE:   [start + go_seconds, end)         -> nombre + barra de progreso
      DONE:     [end, end + outro_seconds)        -> "COMPLETADO" + fade out
    """

    BG = (22, 24, 28, 215)
    ACCENT = (34, 196, 230, 255)
    GO_COLOR = (46, 204, 113, 255)
    TEXT = (255, 255, 255, 255)
    SUBTLE = (150, 155, 160, 255)
    PR_BADGE = (255, 176, 32, 255)

    def __init__(
            self,
            segments_file: Path,
            entry: Callable[[], object],
            at: Coordinate,
            width: int = 900,
            font=None,
            preview_seconds: float = 6.0,
            go_seconds: float = 2.0,
            outro_seconds: float = 3.0,
    ):
        self.entry = entry
        self.at = at
        self.width = width
        self.preview_seconds = preview_seconds
        self.go_seconds = go_seconds
        self.outro_seconds = outro_seconds

        raw = json.loads(Path(segments_file).read_text(encoding="utf-8"))
        self.segments: List[_Segment] = []
        for s in raw.get("segments", []):
            self.segments.append(_Segment(
                id=str(s.get("id", "")),
                name=s.get("name", "Segmento"),
                start=_parse_dt(s["start_time"]),
                end=_parse_dt(s["end_time"]),
                distance_m=float(s.get("distance_m") or 0),
                pr_rank=s.get("pr_rank"),
            ))
        self.segments.sort(key=lambda s: s.start)

        f = font if font is not None else (lambda size, name=None: None)
        self.font_title = f(26, "BarlowCondensed-SemiBold.ttf")
        self.font_name = f(52, "BarlowCondensed-Bold.ttf")
        self.font_sub = f(34, "BarlowCondensed-SemiBold.ttf")
        self.font_badge = f(28, "BarlowCondensed-Bold.ttf")

        self._pad = 26
        self._height = 0
        self._card = None

    # --------------------------------------------------------------
    def _now(self) -> Optional[datetime]:
        e = self.entry()
        if e is None or e.dt is None:
            return None
        dt = e.dt
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    def _find_segment(self, now: datetime):
        """Devuelve (seg, state, progress) del segmento que toca, si hay."""
        best = None
        for s in self.segments:
            inc_t = s.start.timestamp() - self.preview_seconds
            if inc_t <= now.timestamp() < s.start.timestamp():
                p = _clamp01((now.timestamp() - inc_t) / self.preview_seconds)
                return s, "incoming", p
            if s.start.timestamp() <= now.timestamp() < s.end.timestamp():
                total = max(1.0, s.end.timestamp() - s.start.timestamp())
                p = _clamp01((now.timestamp() - s.start.timestamp()) / total)
                if now.timestamp() - s.start.timestamp() < self.go_seconds:
                    return s, "go", _clamp01((now.timestamp() - s.start.timestamp()) / self.go_seconds)
                return s, "active", p
            if s.end.timestamp() <= now.timestamp() < s.end.timestamp() + self.outro_seconds:
                p = _clamp01((now.timestamp() - s.end.timestamp()) / self.outro_seconds)
                return s, "done", p
            if s.start.timestamp() > now.timestamp() and best is None:
                best = s
        return None, "hidden", 0.0

    # --------------------------------------------------------------
    def _rounded_card(self, w: int, h: int, fill=BG, radius=22, accent=None) -> Image.Image:
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=fill)
        if accent is not None:
            d.rounded_rectangle([0, 0, 10, h - 1], radius=radius, fill=accent)
            d.rectangle([10, 0, 16, h - 1], fill=accent)
        return img

    def _compose(self, title, title_rgb, name, right_text, badge, progress=None,
                 accent=ACCENT) -> Image.Image:
        h = 150 if progress is None else 178
        card = self._rounded_card(self.width, h, accent=accent)
        d = ImageDraw.Draw(card)
        x0 = self._pad + 12

        d.text((x0, 14), title, font=self.font_title, fill=title_rgb)
        d.text((x0, 50), name, font=self.font_name, fill=self.TEXT)

        if right_text:
            w = d.textlength(right_text, font=self.font_sub)
            d.text((self.width - self._pad - w, 64), right_text, font=self.font_sub, fill=self.SUBTLE)

        if badge:
            bw = d.textlength(badge, font=self.font_badge) + 24
            bx = self.width - self._pad - bw
            d.rounded_rectangle([bx, 12, bx + bw, 44], radius=16, outline=self.PR_BADGE, width=2)
            d.text((bx + 12, 16), badge, font=self.font_badge, fill=self.PR_BADGE)

        if progress is not None:
            y = h - 26
            d.rounded_rectangle([x0, y, self.width - self._pad, y + 8], radius=4, fill=(70, 74, 80, 255))
            px = x0 + (self.width - self._pad - x0) * _clamp01(progress)
            if px > x0:
                d.rounded_rectangle([x0, y, px, y + 8], radius=4, fill=accent)

        return card

    def _blit(self, image: Image, card: Image.Image, dy: float = 0.0, alpha: float = 1.0):
        if alpha < 1.0:
            card = card.copy()
            card.putalpha(card.getchannel("A").point(lambda a: int(a * alpha)))
        image.alpha_composite(card, (int(self.at.x), int(self.at.y + dy)))

    # --------------------------------------------------------------
    def draw(self, image: Image, draw: ImageDraw):
        now = self._now()
        if now is None:
            return
        seg, state, p = self._find_segment(now)
        if seg is None:
            return

        name = seg.name.strip()
        dist_txt = f"{seg.distance_m / 1000:.1f} km"
        badge = f"PR #{seg.pr_rank}" if seg.pr_rank else None

        if state == "incoming":
            ease = _ease_out_cubic(p)
            card = self._compose("PRÓXIMO SEGMENTO", self.ACCENT, name, dist_txt, badge)
            self._blit(image, card, dy=-60 * (1 - ease), alpha=ease)
        elif state == "go":
            # flash: aparece ya dentro, con leve zoom-out
            scale = 1.0 + 0.06 * (1 - p)
            card = self._compose("¡SEGMENTO!", self.GO_COLOR, name, dist_txt, badge,
                                 accent=self.GO_COLOR)
            if abs(scale - 1.0) > 0.001:
                w2, h2 = int(card.width * scale), int(card.height * scale)
                card = card.resize((w2, h2), Image.LANCZOS)
                self._blit(image, card, dy=-(h2 - card.height) / 2)
            else:
                self._blit(image, card)
        elif state == "active":
            card = self._compose("EN SEGMENTO", self.ACCENT, name, dist_txt, badge,
                                 progress=p)
            self._blit(image, card)
        elif state == "done":
            card = self._compose("COMPLETADO", self.SUBTLE, name, dist_txt, badge,
                                 accent=self.SUBTLE)
            self._blit(image, card, alpha=1 - p)
