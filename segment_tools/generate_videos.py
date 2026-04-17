#!/usr/bin/env python3
"""
Genera videos individuales de leaderboard para cada segmento Strava.
Soporta entrada por JSON o CSV (con columna Highlight=1 para marcar tu fila).

Uso (JSON):
    python generate_videos.py --segments segments.json --output-dir ./out/

Uso (CSV):
    python generate_videos.py --segments leaderboard_2294430.csv --output-dir ./out/

Opciones:
    --duration 12   Duración en segundos (default: 12)
    --fps 60        FPS (default: 60)
    --width 650     Ancho del video
    --height 550    Alto del video
    --font path.ttf Fuente TTF opcional
    --filter texto  Filtrar segmentos por nombre
"""

import argparse
import csv
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Dict, Optional

from PIL import Image, ImageDraw, ImageFont, ImageFilter


def log(msg: str):
    print(f"[VIDEO] {msg}")


# ═══════════════════════════════════════════════════════════════════════════════
# Easing functions
# ═══════════════════════════════════════════════════════════════════════════════

def clamp(t: float, lo=0.0, hi=1.0) -> float:
    return max(lo, min(hi, t))


def ease_in_out_cubic(t: float) -> float:
    t = clamp(t)
    return 4 * t * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def ease_out_cubic(t: float) -> float:
    return 1 - (1 - clamp(t)) ** 3


def ease_out_quart(t: float) -> float:
    return 1 - (1 - clamp(t)) ** 4


def ease_in_cubic(t: float) -> float:
    return clamp(t) ** 3


def ease_out_bounce(t: float) -> float:
    t = clamp(t)
    n1, d1 = 7.5625, 2.75
    if t < 1 / d1:
        return n1 * t * t
    elif t < 2 / d1:
        t -= 1.5 / d1
        return n1 * t * t + 0.75
    elif t < 2.5 / d1:
        t -= 2.25 / d1
        return n1 * t * t + 0.9375
    else:
        t -= 2.625 / d1
        return n1 * t * t + 0.984375


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * clamp(t)


def lerp_color(c1: tuple, c2: tuple, t: float) -> tuple:
    t = clamp(t)
    return tuple(int(a + (b - a) * t) for a, b in zip(c1[:4], c2[:4]))


def with_alpha(color: tuple, alpha: float) -> tuple:
    """Devuelve el color con alpha multiplicado por alpha (0.0–1.0)."""
    base_a = color[3] if len(color) == 4 else 255
    return (*color[:3], int(base_a * clamp(alpha)))


# ═══════════════════════════════════════════════════════════════════════════════
# Generador
# ═══════════════════════════════════════════════════════════════════════════════

class LeaderboardVideoGenerator:

    # ── Paleta de colores ──────────────────────────────────────────────────
    BG             = (15,  15,  20,  235)
    PANEL_BORDER   = (255, 100,  0,  160)
    HEADER         = (215,  65,  0,  255)   # Naranja Strava
    HEADER_TOP     = (255, 120, 20,  255)   # Acento superior
    TEXT           = (255, 255, 255, 255)
    DIM            = (255, 255, 255, 255)
    HIGHLIGHT      = (255, 255, 255, 255)
    HIGHLIGHT_GLOW = (255, 160,   0,  90)
    ROW_ODD        = ( 42,  44,  52, 210)
    ROW_EVEN       = ( 32,  34,  41, 210)
    SCAN_ROW       = ( 60,  55,  28, 235)
    MY_ROW         = ( 68,  52,   8, 245)
    MY_ROW_PULSE   = (120,  95,  15, 250)
    COL_HEADER_BG  = ( 52,  54,  62, 175)
    SEPARATOR      = (255, 100,   0, 110)
    GOLD           = (255, 200,  50, 255)
    SILVER         = (200, 200, 210, 255)
    BRONZE         = (200, 130,  70, 255)

    def __init__(self, output_dir: Path, duration: float = 15.0, fps: int = 60,
                 width: int = 650, height: int = 550, font_path: Path = None,
                 panel_scale: float = 0.70):
        self.base_width  = 650
        self.base_height = 550
        self.output_dir  = output_dir
        self.duration    = duration
        self.fps         = fps
        self.width       = width
        self.height      = height
        self.panel_scale = max(0.35, min(1.0, panel_scale))
        self.total_frames = int(duration * fps)
        self.stage_width  = int(round(self.width * self.panel_scale))
        self.stage_height = int(round(self.height * self.panel_scale))
        self.stage_x      = (self.width - self.stage_width) // 2
        self.stage_y      = (self.height - self.stage_height) // 2
        self.scale_x      = self.stage_width / self.base_width
        self.scale_y      = self.stage_height / self.base_height
        self.scale       = min(self.scale_x, self.scale_y)
        self._init_font(font_path)
        self._init_assets()
        self._init_layout()

    def px(self, value: float, min_px: int = 1) -> int:
        return max(min_px, int(round(value)))

    def sx(self, value: float, min_px: int = 1) -> int:
        return self.px(value * self.scale_x, min_px=min_px)

    def sy(self, value: float, min_px: int = 1) -> int:
        return self.px(value * self.scale_y, min_px=min_px)

    def ss(self, value: float, min_px: int = 1) -> int:
        return self.px(value * self.scale, min_px=min_px)

    def _init_layout(self):
        # Layout basado en el diseño 650x550 y escalado proporcional.
        self.margin = self.sx(20)

        self.col_rank_x  = self.stage_x + self.margin + self.sx(12)   # Posición de N°
        self.col_name_x  = self.stage_x + self.margin + self.sx(58)   # Posición de Nombre
        self.col_date_x  = self.stage_x + self.margin + self.sx(240)  # Posición de Fecha
        self.col_speed_x = self.stage_x + self.margin + self.sx(430)  # Posición de Km/h
        self.col_time_x  = self.stage_x + self.margin + self.sx(470)  # Posición de Tiempo

        self.header_h         = self.sy(50)
        self.col_header_h     = self.sy(32)  # Aumentado de 26 para evitar superposición con texto grande
        self.row_h            = self.sy(38)
        self.panel_top_gap    = self.sy(10)
        self.panel_bottom_pad = self.sy(15)
        self.extra_gap        = self.sy(5)
        self.extra_sep_h      = self.sy(18)
        self.extra_bottom_pad = self.sy(8)

        self.panel_radius = self.ss(12)
        self.panel_border = self.ss(2)
        self.shadow_dx    = self.ss(8)
        self.shadow_dy    = self.ss(8)
        self.shadow_blur  = self.ss(14)

    def _init_font(self, font_path: Path = None):
        candidates = []
        if font_path and Path(font_path).exists():
            candidates.append(str(font_path))
        candidates += [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
            "arial.ttf",
        ]
        self._font_path = None
        for c in candidates:
            try:
                ImageFont.truetype(c, 16)
                self._font_path = c
                log(f"  Fuente: {c}")
                break
            except Exception:
                continue
        if not self._font_path:
            log("  ⚠ Usando fuente de sistema (sin TTF)")

    def _init_assets(self):
        self.crown_icon = None
        self._crown_cache = {}
        crown_path = Path(__file__).parent / "crown_icon.png"
        if crown_path.exists():
            try:
                self.crown_icon = Image.open(crown_path).convert("RGBA")
                log(f"  Crown icon: {crown_path.name}")
            except Exception:
                self.crown_icon = None

    def font(self, size: int) -> ImageFont.ImageFont:
        if self._font_path:
            try:
                return ImageFont.truetype(self._font_path, size)
            except Exception:
                pass
        return ImageFont.load_default()

    # ── Helpers de dibujo ─────────────────────────────────────────────────

    def rank_color(self, rank: int) -> tuple:
        if rank == 1: return self.TEXT
        if rank == 2: return self.TEXT
        if rank == 3: return self.TEXT
        return self.TEXT

    def shadow_text(self, draw: ImageDraw.Draw, xy, text, font,
                    color, off=2, shadow_a=80):
        draw.text((xy[0] + off, xy[1] + off), text, font=font,
                  fill=(0, 0, 0, shadow_a))
        draw.text(xy, text, font=font, fill=color)

    def glow_rect(self, img: Image.Image, x1, y1, x2, y2,
                  color=(255, 160, 0, 80), blur=14):
        """Aplica un brillo difuso alrededor de un rectángulo."""
        gl = Image.new('RGBA', img.size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(gl)
        gd.rounded_rectangle([(x1 - 6, y1 - 6), (x2 + 6, y2 + 6)],
                              radius=10, fill=color)
        gl = gl.filter(ImageFilter.GaussianBlur(blur))
        img.alpha_composite(gl)

    def truncate(self, draw: ImageDraw.Draw, text: str, font, max_w: int) -> str:
        bbox = draw.textbbox((0, 0), text, font=font)
        while bbox[2] > max_w and len(text) > 6:
            text = text[:-4] + "..."
            bbox = draw.textbbox((0, 0), text, font=font)
        return text

    # ── Panel base ────────────────────────────────────────────────────────

    def _calc_panel_layout(self, segment: Dict) -> tuple:
        """Calcula altura del panel y offset cuando hay fila extra fuera del top 10."""
        leaderboard = segment.get('leaderboard', [])
        my_pos = segment.get('my_position')
        n_rows = min(len(leaderboard), 10)

        outside_top10 = my_pos is not None and int(my_pos) > 10

        # Altura base
        panel_height = (
            self.header_h
            + self.panel_top_gap
            + self.col_header_h
            + (n_rows * self.row_h)
            + self.panel_bottom_pad
        )
        if outside_top10:
            # Mi fila fuera del top 10 ocupa exactamente una fila adicional, sin separadores extra.
            panel_height += self.row_h

        # Centrar el panel verticalmente: mantiene composición alineada en 4k/1080/short.
        default_panel_h = self.stage_height - 2 * self.margin
        dy_offset = (default_panel_h - panel_height) // 2
        return panel_height, dy_offset

    def draw_panel(self, img: Image.Image, draw: ImageDraw.Draw,
                   alpha: float = 1.0, dy: int = 0, panel_height: int = None):
        """Dibuja fondo + borde del panel. Retorna (x1,y1,x2,y2,panel_w,panel_h)."""
        m = self.margin
        pw = self.stage_width - 2 * m
        ph = panel_height if panel_height is not None else (self.stage_height - 2 * m)
        x1, y1 = self.stage_x + m, self.stage_y + m + dy
        x2, y2 = x1 + pw, y1 + ph

        # Panel completamente transparente/sin borde.
        return x1, y1, x2, y2, pw, ph

    def draw_header(self, draw: ImageDraw.Draw, segment: Dict,
                    x1, y1, pw, alpha: float = 1.0) -> int:
        """Dibuja el header moderno con gradiente y efecto de profundidad."""
        hh = self.header_h

        # Sombra sutil debajo del header
        shadow_offset = self.ss(4)
        shadow_color = (0, 0, 0, 60)
        draw.rounded_rectangle(
            [(x1 + shadow_offset, y1 + shadow_offset), (x1 + pw, y1 + hh)],
            radius=self.panel_radius,
            fill=with_alpha(shadow_color, alpha),
        )

        # Fondo principal con gradiente vertical simulado (3 franjas)
        # Color base naranja
        header_base = self.HEADER
        # Color más oscuro para la parte inferior (efecto 3D)
        header_dark = (185, 55, 0, 255)
        # Color más claro para la parte superior (brillo)
        header_light = self.HEADER_TOP

        # Franja superior (brillante)
        light_h = self.sy(15)
        draw.rounded_rectangle(
            [(x1, y1), (x1 + pw, y1 + light_h)],
            radius=self.panel_radius,
            fill=with_alpha(header_light, alpha),
        )
        # Rectángulo para cubrir la parte inferior del radius de arriba
        draw.rectangle(
            [(x1, y1 + light_h // 2), (x1 + pw, y1 + light_h)],
            fill=with_alpha(header_light, alpha),
        )

        # Franja media (color base)
        mid_y1 = y1 + light_h
        mid_h = hh - light_h - self.sy(8)
        draw.rectangle(
            [(x1, mid_y1), (x1 + pw, mid_y1 + mid_h)],
            fill=with_alpha(header_base, alpha),
        )

        # Franja inferior (más oscura - profundidad)
        dark_y1 = mid_y1 + mid_h
        dark_h = self.sy(8)
        draw.rounded_rectangle(
            [(x1, dark_y1), (x1 + pw, y1 + hh)],
            radius=self.panel_radius,
            fill=with_alpha(header_dark, alpha),
        )
        # Rectángulo para cubrir la parte superior del radius de abajo
        draw.rectangle(
            [(x1, dark_y1), (x1 + pw, dark_y1 + dark_h // 2)],
            fill=with_alpha(header_dark, alpha),
        )

        # Nombre del segmento - más grande y bold
        name = segment.get('name', 'Segmento')
        # Fuente más grande para el header
        f = self.font(self.ss(24) if len(name) < 26 else self.ss(20))
        name = self.truncate(draw, name, f, pw - self.sx(40))

        # Sombra del texto más pronunciada para legibilidad
        shadow_off = self.ss(2)
        shadow_txt = (120, 40, 0, 200)
        draw.text((x1 + self.sx(18) + shadow_off, y1 + self.sy(14) + shadow_off),
                  name, font=f, fill=with_alpha(shadow_txt, alpha))
        # Texto principal
        draw.text((x1 + self.sx(18), y1 + self.sy(14)),
                  name, font=f, fill=with_alpha(self.TEXT, alpha))

        return hh

    def draw_col_headers(self, draw: ImageDraw.Draw, x1: int, pw: int, y: int, alpha: float = 1.0):
        bar_y1 = y - self.sy(4)
        bar_y2 = y + self.sy(26)
        # Fondo más visible (más opaco y con un toque de color)
        header_bg = (45, 48, 58, 220)  # Más opaco que COL_HEADER_BG original
        draw.rounded_rectangle(
            [(x1 + self.sx(5), bar_y1), (x1 + pw - self.sx(5), bar_y2)],
            radius=self.ss(8),
            fill=with_alpha(header_bg, alpha),
        )
        # Texto más grande - mismo tamaño que las filas (ss(18))
        f = self.font(self.ss(18))
        c = with_alpha(self.TEXT, alpha)
        draw.text((self.col_rank_x,  y), "N°",     font=f, fill=c)
        draw.text((self.col_name_x,  y), "Nombre", font=f, fill=c)

        # Fecha centrada en su columna
        date_text = "Fecha"
        date_col_width = self.col_speed_x - self.col_date_x - self.sx(10)
        date_w = draw.textbbox((0, 0), date_text, font=f)[2]
        date_x = self.col_date_x + (date_col_width - date_w) // 2
        draw.text((date_x,  y), date_text, font=f, fill=c)

        draw.text((self.col_speed_x, y), "Km/h",   font=f, fill=c)

        # Tiempo centrado en su columna
        time_text = "Tiempo"
        # Ancho disponible desde col_time_x hasta el borde derecho del panel menos margen
        time_col_width = (x1 + pw - self.sx(15)) - self.col_time_x
        time_w = draw.textbbox((0, 0), time_text, font=f)[2]
        time_x = self.col_time_x + (time_col_width - time_w) // 2
        draw.text((time_x, y), time_text, font=f, fill=c)

    def draw_leaderboard_row(self, img: Image.Image, draw: ImageDraw.Draw,
                              entry: Dict, row_y: int, row_h: int,
                              x1: int, pw: int,
                              bg: tuple, text_c: tuple, rank_c: tuple,
                              alpha: float = 1.0, slide_x: int = 0,
                              glow: bool = False, glow_color: tuple = None,
                              rank_override: Optional[int] = None):
        """Dibuja una sola fila del leaderboard."""
        if glow and glow_color:
            self.glow_rect(
                img,
                x1 + self.sx(5),
                row_y,
                x1 + pw - self.sx(5),
                row_y + row_h - self.sy(3),
                glow_color,
                blur=self.ss(12),
            )
            draw = ImageDraw.Draw(img)

        rx1 = x1 + self.sx(5) + slide_x
        draw.rectangle([(rx1, row_y), (x1 + pw - self.sx(5), row_y + row_h - self.sy(3))],
                        fill=with_alpha(bg, alpha))

        # Texto más grande en las filas
        f = self.font(self.ss(18))
        ty = row_y + self.sy(9)
        ox = slide_x  # offset horizontal para texto

        rank = int(rank_override if rank_override is not None else entry.get('rank', 0))
        name_max_w = max(self.sx(40), self.col_date_x - (self.col_name_x + ox) - self.sx(10))
        name_txt = self.truncate(draw, entry.get('name', ''), f, name_max_w)
        rank_x = self.col_rank_x + ox
        if rank == 1:
            # Corona KOM para el primer puesto (estilo Strava), usando crown_icon local.
            crown_y = row_y + self.sy(8)
            crown_size = self.ss(17)
            if self.crown_icon is not None:
                crown_img = self._crown_cache.get(crown_size)
                if crown_img is None:
                    crown_img = self.crown_icon.resize((crown_size, crown_size), Image.LANCZOS)
                    self._crown_cache[crown_size] = crown_img
                icon = crown_img.copy()
                if alpha < 0.999:
                    mask = icon.getchannel("A").point(lambda p: int(p * clamp(alpha)))
                    icon.putalpha(mask)
                img.alpha_composite(icon, dest=(rank_x, crown_y))
            else:
                draw.text((rank_x, ty), "1", font=f, fill=with_alpha(rank_c, alpha))
        else:
            draw.text((rank_x, ty), str(rank), font=f, fill=with_alpha(rank_c, alpha))
        draw.text((self.col_name_x  + ox, ty), name_txt,                    font=f, fill=with_alpha(text_c, alpha))

        # Fecha centrada en su columna
        date_val = entry.get('date', '')
        date_col_width = self.col_speed_x - self.col_date_x - self.sx(10)
        date_w = draw.textbbox((0, 0), date_val, font=f)[2]
        date_x = self.col_date_x + (date_col_width - date_w) // 2
        draw.text((date_x + ox, ty), date_val, font=f, fill=with_alpha(self.DIM, alpha))

        draw.text((self.col_speed_x + ox, ty), str(entry.get('speed_kmh', '')), font=f, fill=with_alpha(text_c, alpha))

        # Tiempo centrado en su columna
        time_val = entry.get('time', '')
        time_col_width = (x1 + pw - self.sx(15)) - self.col_time_x
        time_w = draw.textbbox((0, 0), time_val, font=f)[2]
        time_x = self.col_time_x + (time_col_width - time_w) // 2
        draw.text((time_x + ox, ty), time_val, font=f, fill=with_alpha(text_c, alpha))

    # ══════════════════════════════════════════════════════════════════════════
    # FASE 1 — Intro
    # ══════════════════════════════════════════════════════════════════════════

    def frame_intro(self, segment: Dict, t: float) -> Image.Image:
        """
        Intro compacta en ancho: notificación tipo "chip" centrada, solo el ancho necesario.
        """
        img  = Image.new('RGBA', (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Entrada rápida + hold + salida suave
        in_t   = ease_out_cubic(clamp(t / 0.12))
        out_t  = ease_in_cubic(clamp((t - 0.88) / 0.12))
        alpha  = in_t * (1.0 - out_t)
        slide_y = int((1 - in_t) * self.sy(8))

        # Altura compacta
        box_h = self.sy(40)
        y1 = self.stage_y + self.sy(140) + slide_y
        y2 = y1 + box_h

        # ═══════════════════════════════════════════════════════════════════
        # CONFIGURACIÓN DE ANCHO DEL CHIP - Modificá estos valores si querés
        # ajustar cuánto espacio ocupa la notificación "Próximo segmento"
        # ═══════════════════════════════════════════════════════════════════
        # Ancho máximo para el nombre del segmento (aumentalo si se recorta)
        MAX_NAME_WIDTH = self.sx(700)   # <-- Ajustá este valor (más = más ancho)
        # Espacio entre "Próximo" y el nombre del segmento
        GAP_LABEL_NAME = self.sx(20)    # <-- Espaciado entre textos
        # Padding horizontal del chip
        CHIP_PADDING_X = self.sx(20)    # <-- Espacio alrededor de todo el contenido

        label = "Próximo segmento:"
        name = segment.get('name', 'Segmento')
        # Mismo tamaño de fuente para label y nombre
        fn = self.font(self.ss(18) if len(name) < 30 else self.ss(15))
        fl = fn  # Mismo tamaño que el nombre
        label_w = draw.textbbox((0, 0), label, font=fl)[2]

        # Truncar primero para saber el ancho real que ocupará
        name = self.truncate(draw, name, fn, MAX_NAME_WIDTH)
        name_w = draw.textbbox((0, 0), name, font=fn)[2]

        # Ancho total: padding izq + dot + gap + label + gap + nombre + padding der
        # Ahora con padding explícito en ambos lados
        pad_x = CHIP_PADDING_X
        dot_r = self.ss(5)
        gap = self.sx(8)
        content_w = pad_x + (dot_r * 2) + gap + label_w + GAP_LABEL_NAME + name_w + pad_x

        # Centrar horizontalmente en el stage
        stage_center_x = self.stage_x + self.stage_width // 2
        x1 = stage_center_x - content_w // 2
        x2 = x1 + content_w

        # Fondo oscuro semi-transparente tipo chip
        bg_color = (22, 24, 30, 200)
        draw.rounded_rectangle(
            [(x1, y1), (x2, y2)],
            radius=self.ss(20),
            fill=with_alpha(bg_color, alpha),
        )

        # Indicador naranja circular
        dot_x = x1 + pad_x + dot_r
        dot_y = y1 + box_h // 2
        draw.ellipse(
            [(dot_x - dot_r, dot_y - dot_r), (dot_x + dot_r, dot_y + dot_r)],
            fill=with_alpha(self.HEADER, alpha),
        )

        # Label "Próximo" - mismo color blanco que el nombre, mismo tamaño
        label_x = dot_x + dot_r + gap
        draw.text((label_x, y1 + self.sy(9)),
                  label, font=fl, fill=with_alpha(self.TEXT, alpha))

        # Nombre del segmento - ahora posicionado correctamente con espacio antes del padding derecho
        name_x = label_x + label_w + GAP_LABEL_NAME
        draw.text((name_x, y1 + self.sy(9)),
                  name, font=fn, fill=with_alpha(self.TEXT, alpha))

        return img
    def frame_building(self, segment: Dict, t: float) -> Image.Image:
        """
        Cada fila tiene su propio timing staggered.
        Aparece con slide desde la izquierda + fade.
        """
        leaderboard = segment.get('leaderboard', [])
        n_rows      = min(len(leaderboard), 10)
        row_h       = self.row_h
        col_header_h = self.col_header_h

        # Calcular layout del panel
        panel_height, dy_offset = self._calc_panel_layout(segment)

        img  = Image.new('RGBA', (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        x1, y1, x2, y2, pw, ph = self.draw_panel(img, draw, panel_height=panel_height, dy=dy_offset)
        hh = self.draw_header(draw, segment, x1, y1, pw)

        col_y    = y1 + hh + self.panel_top_gap
        row_st_y = col_y + col_header_h

        # Headers de columna con fade in rápido
        col_alpha = ease_out_cubic(clamp(t * 5))
        self.draw_col_headers(draw, x1, pw, col_y, alpha=col_alpha)

        for i in range(n_rows):
            entry = leaderboard[i]
            rank  = i + 1

            # Cada fila empieza en t = i/(n_rows * 1.1)
            start_t = i / (n_rows * 1.1)
            row_t   = ease_out_cubic(clamp((t - start_t) / 0.18))

            if row_t < 0.01:
                continue

            ry      = row_st_y + i * row_h
            slide_x = int((1 - row_t) * -self.sx(65))
            row_bg  = self.ROW_ODD if i % 2 == 0 else self.ROW_EVEN

            self.draw_leaderboard_row(
                img, draw, entry, ry, row_h, x1, pw,
                bg=row_bg,
                text_c=self.TEXT,
                rank_c=self.rank_color(rank),
                alpha=row_t,
                slide_x=slide_x,
                rank_override=rank,
            )
            # Re-obtener draw después de posibles composites
            draw = ImageDraw.Draw(img)

        return img

    # ══════════════════════════════════════════════════════════════════════════
    # FASE 3 — Position (scan + highlight)
    # ══════════════════════════════════════════════════════════════════════════

    def frame_position(self, segment: Dict, t: float) -> Image.Image:
        """
        Sub-fases:
          Si my_pos <= 10:
            0.0–0.45  scan de filas de arriba hacia tu posición
            0.45–1.0  tu fila pulsa con glow

          Si my_pos > 10:
            0.0–0.35  scan completo de las 10 filas
            0.35–0.60 tu fila aparece desde abajo con bounce
            0.60–1.0  tu fila pulsa
        """
        img  = Image.new('RGBA', (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        leaderboard = segment.get('leaderboard', [])
        my_pos      = segment.get('my_position')   # int o None
        n_rows      = min(len(leaderboard), 10)
        outside_top10 = my_pos is not None and int(my_pos) > 10

        # Calcular layout del panel
        panel_height, dy_offset = self._calc_panel_layout(segment)

        x1, y1, x2, y2, pw, ph = self.draw_panel(img, draw, panel_height=panel_height, dy=dy_offset)
        hh = self.draw_header(draw, segment, x1, y1, pw)

        col_y    = y1 + hh + self.panel_top_gap
        row_h    = self.row_h
        row_st_y = col_y + self.col_header_h

        self.draw_col_headers(draw, x1, pw, col_y)

        # ── Timing de sub-fases ──
        if my_pos is not None and int(my_pos) > 10:
            scan_end    = 0.35
            appear_start = 0.35
            appear_end   = 0.58
            pulse_start  = 0.58
        else:
            scan_end    = 0.45
            pulse_start  = 0.45

        # Índice de fila "scaneada" (float, para interpolación suave)
        target_idx = (int(my_pos) - 1) if (my_pos and not outside_top10) else (n_rows - 1)

        if t < scan_end:
            scan_t   = ease_in_out_cubic(t / scan_end)
            scan_idx = scan_t * target_idx  # float 0 → target_idx
        else:
            scan_idx = target_idx  # se detiene en el target

        # Pulso en la fila target / mi fila
        pulse = 0.0
        if t > pulse_start:
            pt    = (t - pulse_start) / (1.0 - pulse_start)
            pulse = math.sin(pt * math.pi * 5.5) * 0.5 + 0.5

        # ── Dibujar las 10 filas del top ──
        for i in range(n_rows):
            entry = leaderboard[i]
            rank  = i + 1
            ry    = row_st_y + i * row_h

            # Distancia al cursor de scan
            dist_to_scan = abs(i - scan_idx)
            is_scan      = dist_to_scan < 0.75 and t < scan_end
            is_target    = (i == target_idx) and not outside_top10

            if is_target and t >= pulse_start:
                # Fila que ES el usuario (dentro del top 10): glow + pulso
                pulse_bg = lerp_color(self.MY_ROW, self.MY_ROW_PULSE, pulse)
                self.draw_leaderboard_row(
                    img, draw, entry, ry, row_h, x1, pw,
                    bg=pulse_bg, text_c=self.HIGHLIGHT, rank_c=self.HIGHLIGHT,
                    glow=True, glow_color=with_alpha(self.HIGHLIGHT_GLOW, 0.6 + 0.4 * pulse),
                    rank_override=rank,
                )
            elif is_scan:
                scan_intensity = 1 - dist_to_scan / 0.75
                bg = lerp_color(
                    self.ROW_ODD if i % 2 == 0 else self.ROW_EVEN,
                    self.SCAN_ROW,
                    ease_out_cubic(scan_intensity),
                )
                self.draw_leaderboard_row(
                    img, draw, entry, ry, row_h, x1, pw,
                    bg=bg, text_c=self.TEXT, rank_c=self.rank_color(rank),
                    rank_override=rank,
                )
            else:
                # Fila en reposo
                # Si ya pasó el scan, la fila target (en top 10) queda resaltada
                if is_target and t >= scan_end:
                    bg = lerp_color(self.MY_ROW, self.MY_ROW_PULSE, pulse * 0.5)
                    self.draw_leaderboard_row(
                        img, draw, entry, ry, row_h, x1, pw,
                        bg=bg, text_c=self.HIGHLIGHT, rank_c=self.HIGHLIGHT,
                        rank_override=rank,
                    )
                else:
                    bg = self.ROW_ODD if i % 2 == 0 else self.ROW_EVEN
                    self.draw_leaderboard_row(
                        img, draw, entry, ry, row_h, x1, pw,
                        bg=bg, text_c=self.TEXT, rank_c=self.rank_color(rank),
                        rank_override=rank,
                    )

            draw = ImageDraw.Draw(img)

        # ── Mi fila fuera del top 10 ──
        if outside_top10 and t >= appear_start:
            appear_t   = ease_out_bounce(clamp((t - appear_start) / (appear_end - appear_start)))
            my_row_y   = row_st_y + n_rows * row_h
            slide_yd   = int((1 - appear_t) * self.sy(45))  # sube desde abajo

            # Glow
            if appear_t > 0.4:
                ga = 0.4 + 0.5 * pulse
                self.glow_rect(img,
                               x1 + self.sx(5), my_row_y + slide_yd,
                               x1 + pw - self.sx(5), my_row_y + row_h - self.sy(3) + slide_yd,
                               with_alpha(self.HIGHLIGHT_GLOW, ga), blur=self.ss(14))
                draw = ImageDraw.Draw(img)

            # Fondo
            my_bg = lerp_color(self.MY_ROW, self.MY_ROW_PULSE, pulse * appear_t)
            draw.rectangle(
                [(x1 + self.sx(5), my_row_y + slide_yd),
                 (x1 + pw - self.sx(5), my_row_y + row_h - self.sy(3) + slide_yd)],
                fill=my_bg,
            )

            # Texto - mismo tamaño que las demás filas
            fn  = self.font(self.ss(18))
            hl  = self.HIGHLIGHT
            ty  = my_row_y + self.sy(9) + slide_yd
            draw.text((self.col_rank_x,  ty), str(my_pos),                           font=fn, fill=hl)
            draw.text((self.col_name_x,  ty), str(segment.get('my_name') or "Mauro en Bici"), font=fn, fill=hl)

            # Fecha centrada en su columna
            my_date = str(segment.get('my_date') or "")
            date_col_width = self.col_speed_x - self.col_date_x - self.sx(10)
            date_w = draw.textbbox((0, 0), my_date, font=fn)[2]
            date_x = self.col_date_x + (date_col_width - date_w) // 2
            draw.text((date_x,  ty), my_date, font=fn, fill=hl)

            draw.text((self.col_speed_x, ty), str(segment.get('my_speed') or ""),    font=fn, fill=hl)

            # Tiempo centrado en su columna
            my_time = str(segment.get('my_time') or "")
            time_col_width = (x1 + pw - self.sx(15)) - self.col_time_x
            time_w = draw.textbbox((0, 0), my_time, font=fn)[2]
            time_x = self.col_time_x + (time_col_width - time_w) // 2
            draw.text((time_x,  ty), my_time, font=fn, fill=hl)

        return img

    # ══════════════════════════════════════════════════════════════════════════
    # FASE 4 — Closing
    # ══════════════════════════════════════════════════════════════════════════

    def frame_closing(self, segment: Dict, t: float) -> Image.Image:
        """Cierre limpio: se mantiene el leaderboard y luego se oculta con fade + slide."""
        base = self.frame_position(segment, 1.0)
        hold_ratio = 0.33  # pequeño hold antes de ocultar
        if t < hold_ratio:
            ease_t = 0.0
        else:
            ease_t = ease_in_cubic(clamp((t - hold_ratio) / (1.0 - hold_ratio)))
        alpha = 1.0 - ease_t
        slide_y = int(ease_t * -self.sy(55))

        if alpha < 0.999:
            r, g, b, a = base.split()
            a = a.point(lambda p: int(p * clamp(alpha)))
            base = Image.merge("RGBA", (r, g, b, a))

        img = Image.new('RGBA', (self.width, self.height), (0, 0, 0, 0))
        img.paste(base, (0, slide_y), base)
        return img

    # ══════════════════════════════════════════════════════════════════════════
    # Generar video completo
    # ══════════════════════════════════════════════════════════════════════════

    def generate_video(self, segment: Dict, output_file: Path) -> bool:
        # Timing total = 15 s por defecto
        #  Fase 1 – Intro:     5.0 s (incluye +3 s de pre-aviso)
        #  Fase 2 – Building:  3.0 s
        #  Fase 3 – Position:  resto disponible
        #  Fase 4 – Closing:   1.5 s
        intro_dur    = 5.0
        build_dur    = 3.0
        closing_dur  = 1.5
        position_dur = max(1.0, self.duration - (intro_dur + build_dur + closing_dur))

        f_intro    = int(intro_dur    * self.fps)
        f_build    = int(build_dur    * self.fps)
        f_position = int(position_dur * self.fps)
        f_closing  = int(closing_dur  * self.fps)

        # Ajustar diferencia de redondeo a la fase de posición
        diff = self.total_frames - (f_intro + f_build + f_position + f_closing)
        f_position += diff

        log(f"  Fases: Intro({f_intro}) Build({f_build}) Position({f_position}) Closing({f_closing})")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            gf  = 0  # global frame counter

            phases = [
                (f_intro,    lambda i, n: self.frame_intro(segment,    i / n)),
                (f_build,    lambda i, n: self.frame_building(segment, i / n)),
                (f_position, lambda i, n: self.frame_position(segment, i / n)),
                (f_closing,  lambda i, n: self.frame_closing(segment,  i / n)),
            ]

            for (count, gen) in phases:
                for i in range(count):
                    frame = gen(i, count)
                    frame.save(tmp / f"frame_{gf:05d}.png")
                    gf += 1
                    if gf % 60 == 0:
                        log(f"  Frame {gf}/{self.total_frames}")

            log("  Codificando con FFmpeg...")
            cmd = [
                "ffmpeg", "-y",
                "-framerate", str(self.fps),
                "-i", str(tmp / "frame_%05d.png"),
                "-c:v", "qtrle",
                "-pix_fmt", "argb",
                "-an",
                str(output_file),
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                log(f"  Error FFmpeg: {res.stderr}")
                return False

        return True

    def render_preview_frame(self, segment: Dict, phase: str = "position", t: float = 0.8) -> Image.Image:
        """Renderiza un frame estático para previsualización."""
        t = clamp(t)
        phase = (phase or "position").lower()
        if phase == "intro":
            return self.frame_intro(segment, t)
        if phase == "building":
            return self.frame_building(segment, t)
        if phase == "closing":
            return self.frame_closing(segment, t)
        return self.frame_position(segment, t)


# ═══════════════════════════════════════════════════════════════════════════════
# Carga de datos
# ═══════════════════════════════════════════════════════════════════════════════

def load_from_csv(csv_file: Path) -> List[Dict]:
    """
    Carga segmentos desde un CSV con columnas:
    SegmentID, SegmentName, Rank, Nombre, Fecha, KM/H, Segundos, Highlight

    Highlight=1 marca la fila del usuario (puede estar fuera del top 10).
    """
    segments_map: Dict[str, Dict] = {}

    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            seg_id = row['SegmentID'].strip()
            if seg_id not in segments_map:
                segments_map[seg_id] = {
                    'id':          seg_id,
                    'name':        row['SegmentName'].strip(),
                    'leaderboard': [],
                    'my_position': None,
                    'my_name':     None,
                    'my_date':     None,
                    'my_time':     None,
                    'my_speed':    None,
                }

            entry = {
                'rank':      row['Rank'].strip(),
                'name':      row['Nombre'].strip(),
                'date':      row['Fecha'].strip(),
                'speed_kmh': row['KM/H'].strip(),
                'time':      row['Segundos'].strip(),
            }

            is_me = row.get('Highlight', '0').strip() == '1'

            if is_me:
                s = segments_map[seg_id]
                s['my_position'] = int(row['Rank'].strip())
                s['my_name']     = row['Nombre'].strip()
                s['my_date']     = row['Fecha'].strip()
                s['my_time']     = row['Segundos'].strip()
                s['my_speed']    = row['KM/H'].strip()
                # NO se agrega al leaderboard (se muestra separado si > 10)
            else:
                segments_map[seg_id]['leaderboard'].append(entry)

    return list(segments_map.values())


def create_sample_leaderboard(segment_name: str) -> List[Dict]:
    names = ["Marco R.", "Lucia S.", "Carlos M.", "Ana P.", "Diego L.",
             "Sofia G.", "Juan R.", "Maria T.", "Pedro A.", "Laura N."]
    lb = []
    for i in range(10):
        secs = 120 + i * 15
        lb.append({
            'rank':      str(i + 1),
            'name':      names[i],
            'date':      '15/04/26',
            'speed_kmh': f"{35.0 - i * 1.5:.1f}",
            'time':      f"{secs // 60}:{secs % 60:02d}",
        })
    return lb


def load_from_json(json_file: Path) -> List[Dict]:
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    segments = []
    for seg in data.get('segments', []):
        lb = seg.get('leaderboard', [])
        if not lb:
            log(f"  ⚠ Sin leaderboard para '{seg['name']}', usando datos de ejemplo")
            lb          = create_sample_leaderboard(seg['name'])
            my_position = 7
            my_name     = "Mauro en Bici"
            my_date     = "15/04/26"
            my_time     = "2:45"
            my_speed    = "28.5"
        else:
            my_position = seg.get('my_position')
            my_name     = seg.get('my_name')
            my_date     = seg.get('my_date')
            my_time     = seg.get('my_time')
            my_speed    = seg.get('my_speed')

            # Fallback: si my_* no viene en raíz, intentar inferir desde leaderboard.
            target_names = [my_name, "Mauro Kinjuk", "Mauro en Bici"]
            target_names = [n.strip().lower() for n in target_names if isinstance(n, str) and n.strip()]

            def _to_int(v):
                try:
                    return int(v)
                except Exception:
                    return None

            me_row = None
            if target_names:
                for e in lb:
                    nm = str(e.get('name', '')).strip().lower()
                    if nm in target_names:
                        me_row = e
                        break
            if me_row is None and my_position is not None:
                pos_int = _to_int(my_position)
                if pos_int is not None:
                    for e in lb:
                        if _to_int(e.get('rank')) == pos_int:
                            me_row = e
                            break

            if me_row is not None:
                if my_position is None:
                    my_position = _to_int(me_row.get('rank'))
                if not my_name:
                    my_name = me_row.get('name')
                if not my_date:
                    my_date = me_row.get('date')
                if not my_time:
                    my_time = me_row.get('time')
                if not my_speed:
                    my_speed = me_row.get('speed_kmh')
        segments.append({
            'id':          seg['id'],
            'name':        seg['name'],
            'leaderboard': lb,
            'my_position': my_position,
            'my_name':     my_name,
            'my_date':     my_date,
            'my_time':     my_time,
            'my_speed':    my_speed,
        })
    return segments


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Genera videos de leaderboard para segmentos Strava"
    )
    parser.add_argument("--segments",    type=Path, required=True,
                        help="JSON o CSV con datos de segmentos")
    parser.add_argument("--output-dir",  type=Path, default=Path("./segment_videos"))
    parser.add_argument("--duration",    type=float, default=15.0)
    parser.add_argument("--fps",         type=int,   default=60)
    parser.add_argument("--width",       type=int,   default=650)
    parser.add_argument("--height",      type=int,   default=550)
    parser.add_argument("--preset",      type=str,   default=None,
                        choices=["4k", "1080", "short"],
                        help="Preset de salida: 4k=3840x2160, 1080=1920x1080, short=1080x1920")
    parser.add_argument("--panel-scale", type=float, default=0.70,
                        help="Fracción del encuadre que ocupa el layout (0.35–1.0). Default: 0.70")
    parser.add_argument("--font",        type=Path,  default=None)
    parser.add_argument("--filter",      type=str,   default=None,
                        help="Filtrar segmentos por nombre (substring)")
    parser.add_argument("--limit",       type=int,   default=None,
                        help="Limitar cantidad de segmentos a procesar")
    parser.add_argument("--preview-image", action="store_true",
                        help="Renderiza PNG de preview en vez de generar video")
    parser.add_argument("--preview-phase", type=str, default="position",
                        choices=["intro", "building", "position", "closing"],
                        help="Fase a renderizar en preview-image")
    parser.add_argument("--preview-t", type=float, default=0.80,
                        help="Momento normalizado (0.0–1.0) dentro de la fase de preview")
    args = parser.parse_args()

    if not args.segments.exists():
        log(f"Archivo no encontrado: {args.segments}")
        sys.exit(1)

    if args.preset == "4k":
        args.width, args.height = 3840, 2160
    elif args.preset == "1080":
        args.width, args.height = 1920, 1080
    elif args.preset == "short":
        args.width, args.height = 1080, 1920

    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Detectar formato
    ext = args.segments.suffix.lower()
    if ext == '.csv':
        segments = load_from_csv(args.segments)
    else:
        segments = load_from_json(args.segments)

    log(f"Cargados {len(segments)} segmentos")

    if args.filter:
        segments = [s for s in segments if args.filter.lower() in s['name'].lower()]
        log(f"Filtrados: {len(segments)} segmentos")

    if args.limit:
        segments = segments[:args.limit]
        log(f"Limitado a {len(segments)} segmento(s)")

    gen = LeaderboardVideoGenerator(
        output_dir=args.output_dir,
        duration=args.duration,
        fps=args.fps,
        width=args.width,
        height=args.height,
        font_path=args.font,
        panel_scale=args.panel_scale,
    )
    log(f"Salida: {args.width}x{args.height} @ {args.fps}fps | panel={max(0.35, min(1.0, args.panel_scale)):.2f}")

    ok = 0
    for i, seg in enumerate(segments, 1):
        safe = "".join(c for c in seg['name'] if c.isalnum() or c in ' -_').rstrip()
        safe = safe.replace(' ', '_')[:30]
        if args.preview_image:
            out = args.output_dir / f"segment_{i:02d}_{safe}_preview.png"
        else:
            out = args.output_dir / f"segment_{i:02d}_{safe}.mov"

        log(f"\n[{i}/{len(segments)}] {seg['name']}  (pos: {seg.get('my_position', '?')})")

        if args.preview_image:
            frame = gen.render_preview_frame(seg, phase=args.preview_phase, t=args.preview_t)
            frame.save(out)
            log(f"  ✓ Preview: {out}")
            ok += 1
        else:
            if gen.generate_video(seg, out):
                log(f"  ✓ {out}")
                ok += 1
            else:
                log(f"  ✗ Falló")

    log(f"\n{'='*50}")
    log(f"Completado: {ok}/{len(segments)} — Directorio: {args.output_dir.absolute()}")


if __name__ == "__main__":
    main()
