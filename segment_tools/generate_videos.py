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
    TEXT           = (240, 240, 240, 255)
    DIM            = (155, 155, 165, 255)
    HIGHLIGHT      = (255, 200,   0, 255)   # Amarillo → solo TÚ
    HIGHLIGHT_GLOW = (255, 160,   0,  90)
    ROW_ODD        = ( 42,  44,  52, 210)
    ROW_EVEN       = ( 32,  34,  41, 210)
    SCAN_ROW       = ( 60,  55,  28, 235)
    MY_ROW         = ( 68,  52,   8, 245)
    MY_ROW_PULSE   = (120,  95,  15, 250)
    SEPARATOR      = (255, 100,   0, 110)
    GOLD           = (255, 200,  50, 255)
    SILVER         = (200, 200, 210, 255)
    BRONZE         = (200, 130,  70, 255)

    def __init__(self, output_dir: Path, duration: float = 12.0, fps: int = 60,
                 width: int = 650, height: int = 550, font_path: Path = None):
        self.output_dir  = output_dir
        self.duration    = duration
        self.fps         = fps
        self.width       = width
        self.height      = height
        self.total_frames = int(duration * fps)
        self._init_font(font_path)

        # Columnas (calculadas a partir del margen)
        m = 20
        self.margin      = m
        self.col_rank_x  = m + 12
        self.col_name_x  = m + 58
        self.col_date_x  = m + 278
        self.col_speed_x = m + 420
        self.col_time_x  = m + 510

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

    def font(self, size: int) -> ImageFont.ImageFont:
        if self._font_path:
            try:
                return ImageFont.truetype(self._font_path, size)
            except Exception:
                pass
        return ImageFont.load_default()

    # ── Helpers de dibujo ─────────────────────────────────────────────────

    def rank_color(self, rank: int) -> tuple:
        if rank == 1: return self.GOLD
        if rank == 2: return self.SILVER
        if rank == 3: return self.BRONZE
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
            text = text[:-4] + "…"
            bbox = draw.textbbox((0, 0), text, font=font)
        return text

    # ── Panel base ────────────────────────────────────────────────────────

    def draw_panel(self, img: Image.Image, draw: ImageDraw.Draw,
                   alpha: float = 1.0, dy: int = 0):
        """Dibuja fondo + borde del panel. Retorna (x1,y1,x2,y2,panel_w,panel_h)."""
        m = self.margin
        pw = self.width - 2 * m
        ph = self.height - 2 * m
        x1, y1 = m, m + dy
        x2, y2 = m + pw, m + ph + dy

        # Sombra exterior
        if alpha > 0.25:
            sh = Image.new('RGBA', img.size, (0, 0, 0, 0))
            sd = ImageDraw.Draw(sh)
            sd.rounded_rectangle([(x1 + 8, y1 + 8), (x2 + 8, y2 + 8)],
                                  radius=14, fill=(0, 0, 0, int(75 * alpha)))
            sh = sh.filter(ImageFilter.GaussianBlur(14))
            img.alpha_composite(sh)

        draw.rounded_rectangle([(x1, y1), (x2, y2)], radius=12,
                                fill=with_alpha(self.BG, alpha))
        draw.rounded_rectangle([(x1, y1), (x2, y2)], radius=12,
                                outline=with_alpha(self.PANEL_BORDER, alpha), width=2)
        return x1, y1, x2, y2, pw, ph

    def draw_header(self, draw: ImageDraw.Draw, segment: Dict,
                    x1, y1, pw, alpha: float = 1.0) -> int:
        """Dibuja el header naranja. Retorna la altura del header."""
        hh = 50
        draw.rounded_rectangle([(x1, y1), (x1 + pw, y1 + hh)],
                                radius=12, fill=with_alpha(self.HEADER, alpha))
        # Franja de acento superior
        draw.rectangle([(x1, y1 + 2), (x1 + pw, y1 + 12)],
                        fill=with_alpha(self.HEADER_TOP, alpha))
        # Reaplicar bordes redondeados superiores (el rectangle los tapa)
        draw.rounded_rectangle([(x1, y1), (x1 + pw, y1 + hh)],
                                radius=12, outline=None)

        # Ícono ⚡
        draw.text((x1 + 11, y1 + 14), "⚡", font=self.font(17),
                  fill=with_alpha(self.TEXT, alpha))

        # Nombre del segmento
        name = segment.get('name', 'Segmento')
        f = self.font(21 if len(name) < 28 else 17)
        name = self.truncate(draw, name, f, pw - 80)
        self.shadow_text(draw, (x1 + 36, y1 + 13), name, f,
                         with_alpha(self.TEXT, alpha))
        return hh

    def draw_col_headers(self, draw: ImageDraw.Draw, y: int, alpha: float = 1.0):
        f = self.font(13)
        c = with_alpha(self.DIM, alpha)
        draw.text((self.col_rank_x,  y), "N°",     font=f, fill=c)
        draw.text((self.col_name_x,  y), "Nombre", font=f, fill=c)
        draw.text((self.col_date_x,  y), "Fecha",  font=f, fill=c)
        draw.text((self.col_speed_x, y), "Km/h",   font=f, fill=c)
        draw.text((self.col_time_x,  y), "Tiempo", font=f, fill=c)

    def draw_leaderboard_row(self, img: Image.Image, draw: ImageDraw.Draw,
                              entry: Dict, row_y: int, row_h: int,
                              x1: int, pw: int,
                              bg: tuple, text_c: tuple, rank_c: tuple,
                              alpha: float = 1.0, slide_x: int = 0,
                              glow: bool = False, glow_color: tuple = None):
        """Dibuja una sola fila del leaderboard."""
        if glow and glow_color:
            self.glow_rect(img, x1 + 5, row_y, x1 + pw - 5,
                           row_y + row_h - 3, glow_color, blur=12)
            draw = ImageDraw.Draw(img)

        rx1 = x1 + 5 + slide_x
        draw.rectangle([(rx1, row_y), (x1 + pw - 5, row_y + row_h - 3)],
                        fill=with_alpha(bg, alpha))

        f = self.font(16)
        ty = row_y + 10
        ox = slide_x  # offset horizontal para texto

        rank = int(entry.get('rank', 0))
        draw.text((self.col_rank_x  + ox, ty), str(rank),                   font=f, fill=with_alpha(rank_c, alpha))
        draw.text((self.col_name_x  + ox, ty), entry.get('name', '')[:20],  font=f, fill=with_alpha(text_c, alpha))
        draw.text((self.col_date_x  + ox, ty), entry.get('date', ''),       font=f, fill=with_alpha(self.DIM, alpha))
        draw.text((self.col_speed_x + ox, ty), str(entry.get('speed_kmh', '')), font=f, fill=with_alpha(text_c, alpha))
        draw.text((self.col_time_x  + ox, ty), entry.get('time', ''),       font=f, fill=with_alpha(text_c, alpha))

    # ══════════════════════════════════════════════════════════════════════════
    # FASE 1 — Intro
    # ══════════════════════════════════════════════════════════════════════════

    def frame_intro(self, segment: Dict, t: float) -> Image.Image:
        """
        Panel pequeño que sube desde abajo con bounce. Nombre aparece con fade.
        """
        img  = Image.new('RGBA', (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        slide_t   = ease_out_quart(clamp(t * 1.3))
        alpha     = ease_out_cubic(clamp(t * 2.2))
        dy_offset = int((1 - slide_t) * self.height * 0.32)

        m  = self.margin
        pw = self.width - 2 * m
        ph = int(self.height * 0.42)
        x1 = m
        y1 = (self.height - ph) // 2 + dy_offset
        x2 = m + pw
        y2 = y1 + ph

        # Fondo + borde
        draw.rounded_rectangle([(x1, y1), (x2, y2)], radius=14,
                                fill=with_alpha(self.BG, alpha))
        draw.rounded_rectangle([(x1, y1), (x2, y2)], radius=14,
                                outline=with_alpha(self.PANEL_BORDER, alpha), width=2)

        # Header
        hh = 48
        draw.rounded_rectangle([(x1, y1), (x2, y1 + hh)],
                                radius=12, fill=with_alpha(self.HEADER, alpha))

        sub = "PRÓXIMO SEGMENTO"
        fs  = self.font(13)
        bx  = draw.textbbox((0, 0), sub, font=fs)
        sw  = bx[2] - bx[0]
        draw.text((x1 + (pw - sw) // 2, y1 + 15), sub, font=fs,
                  fill=with_alpha(self.TEXT, alpha))

        # Nombre con fade tardío
        name_t = ease_out_cubic(clamp((t - 0.28) / 0.72))
        if name_t > 0.01:
            name = segment.get('name', 'Segmento')
            fn   = self.font(28 if len(name) < 22 else 22)
            name = self.truncate(draw, name, fn, pw - 60)
            bx   = draw.textbbox((0, 0), name, font=fn)
            nw   = bx[2] - bx[0]
            nx   = x1 + (pw - nw) // 2
            ny   = y1 + hh + 20
            self.shadow_text(draw, (nx, ny), name, fn,
                             with_alpha(self.HIGHLIGHT, name_t), off=3)

        # Flecha con bounce tardío
        arrow_t = ease_out_bounce(clamp((t - 0.65) / 0.35))
        if arrow_t > 0.01:
            fa   = self.font(13)
            atxt = "▼  ver leaderboard  ▼"
            bx   = draw.textbbox((0, 0), atxt, font=fa)
            aw   = bx[2] - bx[0]
            ay   = y2 - 28 + int((1 - arrow_t) * 16)
            draw.text((x1 + (pw - aw) // 2, ay), atxt, font=fa,
                      fill=with_alpha(self.DIM, arrow_t * alpha))

        return img

    # ══════════════════════════════════════════════════════════════════════════
    # FASE 2 — Building (tabla apareciendo fila por fila)
    # ══════════════════════════════════════════════════════════════════════════

    def frame_building(self, segment: Dict, t: float) -> Image.Image:
        """
        Cada fila tiene su propio timing staggered.
        Aparece con slide desde la izquierda + fade.
        """
        img  = Image.new('RGBA', (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        leaderboard = segment.get('leaderboard', [])
        n_rows      = min(len(leaderboard), 10)

        x1, y1, x2, y2, pw, ph = self.draw_panel(img, draw)
        hh = self.draw_header(draw, segment, x1, y1, pw)

        col_y    = y1 + hh + 10
        row_h    = 38
        row_st_y = col_y + 26

        # Headers de columna con fade in rápido
        col_alpha = ease_out_cubic(clamp(t * 5))
        self.draw_col_headers(draw, col_y, alpha=col_alpha)

        for i in range(n_rows):
            entry = leaderboard[i]
            rank  = int(entry.get('rank', i + 1))

            # Cada fila empieza en t = i/(n_rows * 1.1)
            start_t = i / (n_rows * 1.1)
            row_t   = ease_out_cubic(clamp((t - start_t) / 0.18))

            if row_t < 0.01:
                continue

            ry      = row_st_y + i * row_h
            slide_x = int((1 - row_t) * -65)
            row_bg  = self.ROW_ODD if i % 2 == 0 else self.ROW_EVEN

            self.draw_leaderboard_row(
                img, draw, entry, ry, row_h, x1, pw,
                bg=row_bg,
                text_c=self.TEXT,
                rank_c=self.rank_color(rank),
                alpha=row_t,
                slide_x=slide_x,
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

        x1, y1, x2, y2, pw, ph = self.draw_panel(img, draw)
        hh = self.draw_header(draw, segment, x1, y1, pw)

        col_y    = y1 + hh + 10
        row_h    = 38
        row_st_y = col_y + 26

        self.draw_col_headers(draw, col_y)

        outside_top10 = my_pos is not None and int(my_pos) > 10

        # ── Timing de sub-fases ──
        if outside_top10:
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
            rank  = int(entry.get('rank', i + 1))
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
                )
            else:
                # Fila en reposo
                # Si ya pasó el scan, la fila target (en top 10) queda resaltada
                if is_target and t >= scan_end:
                    bg = lerp_color(self.MY_ROW, self.MY_ROW_PULSE, pulse * 0.5)
                    self.draw_leaderboard_row(
                        img, draw, entry, ry, row_h, x1, pw,
                        bg=bg, text_c=self.HIGHLIGHT, rank_c=self.HIGHLIGHT,
                    )
                else:
                    bg = self.ROW_ODD if i % 2 == 0 else self.ROW_EVEN
                    self.draw_leaderboard_row(
                        img, draw, entry, ry, row_h, x1, pw,
                        bg=bg, text_c=self.TEXT, rank_c=self.rank_color(rank),
                    )

            draw = ImageDraw.Draw(img)

        # ── Mi fila fuera del top 10 ──
        if outside_top10 and t >= appear_start:
            appear_t   = ease_out_bounce(clamp((t - appear_start) / (appear_end - appear_start)))
            sep_y      = row_st_y + n_rows * row_h + 5
            my_row_y   = sep_y + 18
            slide_yd   = int((1 - appear_t) * 45)  # sube desde abajo

            # Separador "· · ·"
            sep_alpha = ease_out_cubic(clamp((t - appear_start) / 0.15))
            if sep_alpha > 0.01:
                fs   = self.font(12)
                stxt = "· · · · · · · · · · · · · · · · ·"
                bx   = draw.textbbox((0, 0), stxt, font=fs)
                sw   = bx[2] - bx[0]
                draw.text((x1 + (pw - sw) // 2, sep_y), stxt, font=fs,
                          fill=with_alpha(self.SEPARATOR, sep_alpha))

            # Glow
            if appear_t > 0.4:
                ga = 0.4 + 0.5 * pulse
                self.glow_rect(img,
                               x1 + 5, my_row_y + slide_yd,
                               x1 + pw - 5, my_row_y + row_h - 3 + slide_yd,
                               with_alpha(self.HIGHLIGHT_GLOW, ga), blur=14)
                draw = ImageDraw.Draw(img)

            # Fondo
            my_bg = lerp_color(self.MY_ROW, self.MY_ROW_PULSE, pulse * appear_t)
            draw.rectangle(
                [(x1 + 5, my_row_y + slide_yd),
                 (x1 + pw - 5, my_row_y + row_h - 3 + slide_yd)],
                fill=my_bg,
            )

            # Texto
            fn  = self.font(16)
            hl  = self.HIGHLIGHT
            ty  = my_row_y + 10 + slide_yd
            draw.text((self.col_rank_x,  ty), str(my_pos),                           font=fn, fill=hl)
            draw.text((self.col_name_x,  ty), "TÚ",                                  font=fn, fill=hl)
            draw.text((self.col_speed_x, ty), str(segment.get('my_speed', '')),      font=fn, fill=hl)
            draw.text((self.col_time_x,  ty), str(segment.get('my_time',  '')),      font=fn, fill=hl)

        return img

    # ══════════════════════════════════════════════════════════════════════════
    # FASE 4 — Closing
    # ══════════════════════════════════════════════════════════════════════════

    def frame_closing(self, segment: Dict, t: float) -> Image.Image:
        """Panel se encoge y sube, fundiendo a transparente."""
        img  = Image.new('RGBA', (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        ease_t   = ease_in_cubic(t)
        alpha    = 1.0 - ease_t
        slide_y  = int(ease_t * -55)
        shrink   = ease_t * 0.12

        m  = self.margin
        pw = self.width - 2 * m
        ph = int((self.height - 2 * m) * (1 - shrink))
        x1 = m
        y1 = (self.height - ph) // 2 + slide_y
        x2 = m + pw
        y2 = y1 + ph

        draw.rounded_rectangle([(x1, y1), (x2, y2)], radius=12,
                                fill=with_alpha(self.BG, alpha))

        fn   = self.font(22)
        name = segment.get('name', '')[:35]
        bx   = draw.textbbox((0, 0), name, font=fn)
        nw   = bx[2] - bx[0]
        nx   = x1 + (pw - nw) // 2
        ny   = y1 + ph // 2 - 22
        self.shadow_text(draw, (nx, ny), name, fn,
                         with_alpha(self.HIGHLIGHT, alpha))

        fm   = self.font(14)
        msg  = "¡Segmento completado!"
        bx   = draw.textbbox((0, 0), msg, font=fm)
        mw   = bx[2] - bx[0]
        draw.text((x1 + (pw - mw) // 2, ny + 38), msg, font=fm,
                  fill=with_alpha(self.DIM, alpha))

        return img

    # ══════════════════════════════════════════════════════════════════════════
    # Generar video completo
    # ══════════════════════════════════════════════════════════════════════════

    def generate_video(self, segment: Dict, output_file: Path) -> bool:
        # Timing total = 12 s por defecto
        #  Fase 1 – Intro:     2.0 s
        #  Fase 2 – Building:  3.0 s
        #  Fase 3 – Position:  5.5 s
        #  Fase 4 – Closing:   1.5 s
        intro_dur    = 2.0
        build_dur    = 3.0
        position_dur = 5.5
        closing_dur  = 1.5

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
            my_time     = "2:45"
            my_speed    = "28.5"
        else:
            my_position = seg.get('my_position')
            my_time     = seg.get('my_time')
            my_speed    = seg.get('my_speed')
        segments.append({
            'id':          seg['id'],
            'name':        seg['name'],
            'leaderboard': lb,
            'my_position': my_position,
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
    parser.add_argument("--duration",    type=float, default=12.0)
    parser.add_argument("--fps",         type=int,   default=60)
    parser.add_argument("--width",       type=int,   default=650)
    parser.add_argument("--height",      type=int,   default=550)
    parser.add_argument("--font",        type=Path,  default=None)
    parser.add_argument("--filter",      type=str,   default=None,
                        help="Filtrar segmentos por nombre (substring)")
    args = parser.parse_args()

    if not args.segments.exists():
        log(f"Archivo no encontrado: {args.segments}")
        sys.exit(1)

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

    gen = LeaderboardVideoGenerator(
        output_dir=args.output_dir,
        duration=args.duration,
        fps=args.fps,
        width=args.width,
        height=args.height,
        font_path=args.font,
    )

    ok = 0
    for i, seg in enumerate(segments, 1):
        safe = "".join(c for c in seg['name'] if c.isalnum() or c in ' -_').rstrip()
        safe = safe.replace(' ', '_')[:30]
        out  = args.output_dir / f"segment_{i:02d}_{safe}.mov"

        log(f"\n[{i}/{len(segments)}] {seg['name']}  (pos: {seg.get('my_position', '?')})")

        if gen.generate_video(seg, out):
            log(f"  ✓ {out}")
            ok += 1
        else:
            log(f"  ✗ Falló")

    log(f"\n{'='*50}")
    log(f"Completado: {ok}/{len(segments)} — Directorio: {args.output_dir.absolute()}")


if __name__ == "__main__":
    main()