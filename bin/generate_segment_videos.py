#!/usr/bin/env python3
"""
Genera videos individuales de leaderboard para cada segmento Strava.
NO requiere GPX - genera overlays transparentes directamente.

Uso:
    python bin/generate_segment_videos.py \
        --segments segments_timed.json \
        --output-dir ./segment_videos/ \
        --duration 8 \
        --fps 30
"""

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

from PIL import Image, ImageDraw, ImageFont


def log(msg):
    print(f"[VIDEO] {msg}")


class LeaderboardVideoGenerator:
    """Genera videos de leaderboard para segmentos Strava"""
    
    # Colores
    BG_COLOR = (20, 20, 20, 230)
    HEADER_COLOR = (255, 100, 0, 255)  # Naranja Strava
    TEXT_COLOR = (255, 255, 255, 255)
    HIGHLIGHT_COLOR = (255, 200, 0, 255)
    ROW_BG_1 = (45, 45, 45, 220)
    ROW_BG_2 = (35, 35, 35, 220)
    
    def __init__(self, output_dir: Path, duration: float = 8.0, fps: int = 30,
                 width: int = 800, height: int = 600, font_path: Path = None):
        self.output_dir = output_dir
        self.duration = duration
        self.fps = fps
        self.width = width
        self.height = height
        self.total_frames = int(duration * fps)
        
        # Fuente
        if font_path and font_path.exists():
            self.font_base = ImageFont.truetype(str(font_path), 20)
        else:
            try:
                self.font_base = ImageFont.truetype("arial.ttf", 20)
            except:
                self.font_base = ImageFont.load_default()
    
    def get_font(self, size: int):
        """Obtiene fuente a tamaño específico"""
        try:
            return self.font_base.font_variant(size=size)
        except:
            return self.font_base
    
    def generate_intro_frame(self, segment: Dict, frame: int, total_intro_frames: int) -> Image.Image:
        """Genera frame de animación de entrada"""
        img = Image.new('RGBA', (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Progreso de animación (0.0 a 1.0)
        progress = frame / total_intro_frames
        
        # Escala y opacidad
        scale = 0.5 + (0.5 * progress)
        alpha = int(255 * min(1.0, progress * 2))
        
        # Centro del panel
        center_x = self.width // 2
        center_y = self.height // 2
        
        # Calcular rectángulo escalado
        w = int(self.width * 0.8 * scale)
        h = int(self.height * 0.6 * scale)
        x1 = center_x - w // 2
        y1 = center_y - h // 2
        
        # Fondo
        bg_color = (*self.BG_COLOR[:3], int(self.BG_COLOR[3] * alpha / 255))
        draw.rounded_rectangle([(x1, y1), (x1 + w, y1 + h)], radius=15, fill=bg_color)
        
        # Header con slide
        header_height = 60
        header_slide = int((1 - progress) * -30)
        header_y = y1 + header_slide
        header_color = (*self.HEADER_COLOR[:3], alpha)
        draw.rectangle([(x1, header_y), (x1 + w, header_y + header_height)], 
                      fill=header_color, outline=None)
        
        # Texto "Se aproxima el segmento"
        font_title = self.get_font(22)
        title_text = "Se aproxima el segmento"
        bbox = draw.textbbox((0, 0), title_text, font=font_title)
        title_w = bbox[2] - bbox[0]
        title_x = x1 + (w - title_w) // 2
        title_y = header_y + 15
        draw.text((title_x, title_y), title_text, font=font_title, 
                 fill=(*self.TEXT_COLOR[:3], alpha))
        
        # Nombre del segmento (aparece con delay)
        if progress > 0.3:
            name_progress = min(1.0, (progress - 0.3) / 0.7)
            name_alpha = int(255 * name_progress)
            name = segment.get('name', 'Segmento')
            
            # Truncar si es muy largo
            font_name = self.get_font(32 if len(name) < 25 else 26)
            max_width = w - 60
            bbox = draw.textbbox((0, 0), name, font=font_name)
            while bbox[2] > max_width and len(name) > 10:
                name = name[:-4] + "..."
                bbox = draw.textbbox((0, 0), name, font=font_name)
            
            name_w = bbox[2] - bbox[0]
            name_x = x1 + (w - name_w) // 2
            name_y = y1 + header_height + 50
            
            # Sombra
            shadow_offset = 3
            draw.text((name_x + shadow_offset, name_y + shadow_offset), name, 
                     font=font_name, fill=(0, 0, 0, name_alpha // 3))
            # Texto principal
            draw.text((name_x, name_y), name, font=font_name, 
                     fill=(*self.HIGHLIGHT_COLOR[:3], name_alpha))
            
            # Flecha animada
            if progress > 0.6:
                arrow_bounce = int(((frame - total_intro_frames * 0.6) % 15) / 15 * 15)
                arrow_y = name_y + 60 + arrow_bounce
                font_arrow = self.get_font(40)
                draw.text((center_x - 20, arrow_y), "▼", font=font_arrow, 
                         fill=(*self.TEXT_COLOR[:3], name_alpha))
        
        return img
    
    def generate_leaderboard_frame(self, segment: Dict, frame: int, 
                                   total_leaderboard_frames: int) -> Image.Image:
        """Genera frame del leaderboard"""
        img = Image.new('RGBA', (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Panel principal
        margin = 20
        panel_w = self.width - 2 * margin
        panel_h = self.height - 2 * margin
        
        # Fondo
        draw.rounded_rectangle([(margin, margin), (margin + panel_w, margin + panel_h)], 
                              radius=12, fill=self.BG_COLOR)
        
        # Header
        header_h = 55
        draw.rectangle([(margin, margin), (margin + panel_w, margin + header_h)], 
                      fill=self.HEADER_COLOR)
        
        # Nombre del segmento
        name = segment.get('name', 'Segmento')[:40]
        font_header = self.get_font(24)
        draw.text((margin + 15, margin + 12), name, font=font_header, fill=self.TEXT_COLOR)
        
        # Tabla de leaderboard
        leaderboard = segment.get('leaderboard', [])
        my_pos = segment.get('my_position')
        
        # Columnas
        col_rank_x = margin + 15
        col_name_x = margin + 65
        col_date_x = margin + 280
        col_speed_x = margin + 420
        col_time_x = margin + 520
        
        row_y = margin + header_h + 15
        
        # Headers de columnas
        font_header_row = self.get_font(16)
        header_color = (180, 180, 180, 255)
        draw.text((col_rank_x, row_y), "N°", font=font_header_row, fill=header_color)
        draw.text((col_name_x, row_y), "Nombre", font=font_header_row, fill=header_color)
        draw.text((col_date_x, row_y), "Fecha", font=font_header_row, fill=header_color)
        draw.text((col_speed_x, row_y), "Km/h", font=font_header_row, fill=header_color)
        draw.text((col_time_x, row_y), "Tiempo", font=font_header_row, fill=header_color)
        
        row_y += 35
        
        # Filas del leaderboard
        font_row = self.get_font(17)
        row_height = 38
        
        # Mostrar top 10
        entries_to_show = min(len(leaderboard), 10)
        
        for i in range(entries_to_show):
            entry = leaderboard[i]
            rank = entry.get('rank', str(i + 1))
            name = entry.get('name', '')[:18]
            date = entry.get('date', '')
            speed = entry.get('speed_kmh', '')
            time_str = entry.get('time', '')
            
            # Fila alternada
            row_bg = self.ROW_BG_1 if i % 2 == 0 else self.ROW_BG_2
            is_me = (int(rank) == my_pos) if my_pos else False
            
            if is_me:
                row_bg = (80, 60, 20, 240)  # Resaltar
            
            draw.rectangle([(margin + 5, row_y), (margin + panel_w - 5, row_y + row_height - 3)], 
                          fill=row_bg)
            
            # Color del texto
            text_color = self.HIGHLIGHT_COLOR if is_me else self.TEXT_COLOR
            
            draw.text((col_rank_x, row_y + 8), str(rank), font=font_row, fill=text_color)
            draw.text((col_name_x, row_y + 8), name, font=font_row, fill=text_color)
            draw.text((col_date_x, row_y + 8), date, font=font_row, fill=text_color)
            draw.text((col_speed_x, row_y + 8), str(speed), font=font_row, fill=text_color)
            draw.text((col_time_x, row_y + 8), time_str, font=font_row, fill=text_color)
            
            row_y += row_height
        
        # Si tu posición no está en top 10, agregar al final
        if my_pos and my_pos > 10:
            # Separador
            row_y += 5
            draw.line([(margin + 20, row_y), (margin + panel_w - 20, row_y)], 
                     fill=(100, 100, 100), width=2)
            row_y += 10
            
            # Tu fila
            draw.rectangle([(margin + 5, row_y), (margin + panel_w - 5, row_y + row_height - 3)], 
                          fill=(100, 80, 30, 250))
            
            draw.text((col_rank_x, row_y + 8), str(my_pos), font=font_row, fill=self.HIGHLIGHT_COLOR)
            draw.text((col_name_x, row_y + 8), "TÚ", font=font_row, fill=self.HIGHLIGHT_COLOR)
            draw.text((col_date_x, row_y + 8), "", font=font_row, fill=self.HIGHLIGHT_COLOR)
            draw.text((col_speed_x, row_y + 8), str(segment.get('my_speed', '')), 
                     font=font_row, fill=self.HIGHLIGHT_COLOR)
            draw.text((col_time_x, row_y + 8), segment.get('my_time', ''), 
                     font=font_row, fill=self.HIGHLIGHT_COLOR)
        
        return img
    
    def generate_video(self, segment: Dict, output_file: Path):
        """Genera video completo para un segmento"""
        
        # Dividir duración: 40% intro, 60% leaderboard
        intro_duration = self.duration * 0.4
        leaderboard_duration = self.duration * 0.6
        
        intro_frames = int(intro_duration * self.fps)
        leaderboard_frames = self.total_frames - intro_frames
        
        # Crear directorio temporal para frames
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            
            log(f"Generando {self.total_frames} frames...")
            
            # Generar frames de intro
            for i in range(intro_frames):
                frame = self.generate_intro_frame(segment, i, intro_frames)
                frame.save(tmp_path / f"frame_{i:05d}.png")
                
                if i % 10 == 0:
                    log(f"  Frame {i}/{self.total_frames}")
            
            # Generar frames de leaderboard
            for i in range(leaderboard_frames):
                frame_num = intro_frames + i
                frame = self.generate_leaderboard_frame(segment, i, leaderboard_frames)
                frame.save(tmp_path / f"frame_{frame_num:05d}.png")
                
                if i % 10 == 0:
                    log(f"  Frame {frame_num}/{self.total_frames}")
            
            # Usar FFmpeg para crear video
            log("Codificando video con FFmpeg...")
            
            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-framerate", str(self.fps),
                "-i", str(tmp_path / "frame_%05d.png"),
                "-c:v", "qtrle",  # QuickTime Animation para transparencia
                "-pix_fmt", "argb",
                "-an",  # Sin audio
                str(output_file)
            ]
            
            result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                log(f"Error FFmpeg: {result.stderr}")
                return False
        
        return True


def create_sample_leaderboard(segment_name: str) -> List[Dict]:
    """Crea datos de ejemplo para el leaderboard cuando no hay datos reales"""
    # Datos de ejemplo basados en segmentos típicos de ciclismo
    sample_names = [
        "Marco R.", "Lucia S.", "Carlos M.", "Ana P.", "Diego L.",
        "Sofia G.", "Juan R.", "Maria T.", "Pedro A.", "Laura N."
    ]
    
    leaderboard = []
    for i in range(10):
        rank = i + 1
        # Velocidades realistas de ciclismo
        speed = 35.0 - (i * 1.5)
        # Tiempos acumulados
        total_seconds = 120 + (i * 15)
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        time_str = f"{minutes}:{seconds:02d}"
        
        leaderboard.append({
            'rank': str(rank),
            'name': sample_names[i],
            'date': '15/04/26',
            'speed_kmh': f"{speed:.1f}",
            'time': time_str
        })
    
    return leaderboard


def load_segments(segments_file: Path) -> List[Dict]:
    """Carga segmentos desde JSON"""
    with open(segments_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    segments = []
    for seg in data.get('segments', []):
        leaderboard = seg.get('leaderboard', [])
        
        # Si no hay datos de leaderboard, usar datos de ejemplo
        if not leaderboard:
            log(f"  ⚠️ No hay datos de leaderboard para '{seg['name']}', usando datos de ejemplo")
            leaderboard = create_sample_leaderboard(seg['name'])
            my_position = 7  # Simular que estás en posición 7
            my_time = "2:45"
            my_speed = "28.5"
        else:
            my_position = seg.get('my_position')
            my_time = seg.get('my_time')
            my_speed = seg.get('my_speed')
        
        segments.append({
            'id': seg['id'],
            'name': seg['name'],
            'leaderboard': leaderboard,
            'my_position': my_position,
            'my_time': my_time,
            'my_speed': my_speed,
        })
    
    return segments


def main():
    parser = argparse.ArgumentParser(
        description="Genera videos de leaderboard para segmentos Strava (sin GPX)"
    )
    parser.add_argument("--segments", type=Path, required=True,
                        help="Archivo JSON con datos de segmentos")
    parser.add_argument("--output-dir", type=Path, default=Path("./segment_videos"),
                        help="Directorio de salida")
    parser.add_argument("--duration", type=float, default=8.0,
                        help="Duración de cada video en segundos")
    parser.add_argument("--fps", type=int, default=60,
                        help="FPS del video (default: 60 para animaciones fluidas)")
    parser.add_argument("--width", type=int, default=650,
                        help="Ancho del video")
    parser.add_argument("--height", type=int, default=550,
                        help="Alto del video")
    parser.add_argument("--font", type=Path, default=None,
                        help="Archivo de fuente TTF")
    parser.add_argument("--filter", type=str, default=None,
                        help="Filtrar segmentos por nombre")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limitar cantidad de segmentos a procesar (ej: 1 para solo el primero)")

    args = parser.parse_args()
    
    if not args.segments.exists():
        log(f"No se encontró: {args.segments}")
        sys.exit(1)
    
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    # Cargar segmentos
    segments = load_segments(args.segments)
    log(f"Cargados {len(segments)} segmentos")
    
    if args.filter:
        segments = [s for s in segments if args.filter.lower() in s['name'].lower()]
        log(f"Filtrados: {len(segments)} segmentos")

    if args.limit:
        segments = segments[:args.limit]
        log(f"Limitado a {len(segments)} segmento(s)")

    # Generar videos
    generator = LeaderboardVideoGenerator(
        output_dir=args.output_dir,
        duration=args.duration,
        fps=args.fps,
        width=args.width,
        height=args.height,
        font_path=args.font
    )
    
    success = 0
    for i, segment in enumerate(segments, 1):
        # Sanitizar nombre
        safe_name = "".join(c for c in segment['name'] if c.isalnum() or c in (' ', '-', '_')).rstrip()
        safe_name = safe_name.replace(' ', '_')[:30]
        
        output = args.output_dir / f"segment_{i:02d}_{safe_name}.mov"
        
        log(f"\n[{i}/{len(segments)}] {segment['name']}")
        
        if generator.generate_video(segment, output):
            log(f"  ✓ {output}")
            success += 1
        else:
            log(f"  ✗ Falló")
    
    log(f"\n{'='*50}")
    log(f"Completado: {success}/{len(segments)} videos")
    log(f"Directorio: {args.output_dir.absolute()}")


if __name__ == "__main__":
    main()
