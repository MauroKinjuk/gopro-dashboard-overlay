"""
Segment Overlay Widget - Muestra información de segmentos de Strava

Características:
- Animación de entrada 100m antes del segmento
- Muestra nombre del segmento + leaderboard top 10 + tu posición
- Resalta tu posición en la tabla
- Animación de salida con resumen al completar
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable, Tuple

from PIL import Image, ImageDraw

from gopro_overlay.point import Coordinate
from gopro_overlay.timeseries import Entry
from gopro_overlay.widgets.widgets import Widget, Composite, Translate, Frame
from gopro_overlay.widgets.text import CachingText


@dataclass
class SegmentState:
    """Estado de visualización de un segmento"""
    PREVIEW = "preview"      # 100m antes - animación de entrada
    ACTIVE = "active"        # Dentro del segmento
    COMPLETED = "completed"  # Salida - resumen breve
    HIDDEN = "hidden"        # No visible


class SegmentOverlayWidget(Widget):
    """
    Widget que muestra overlay de segmentos de Strava.
    
    Args:
        segment_data_file: JSON con datos de segmentos temporizados
        entry_provider: Función que retorna el Entry actual del framemeta
        font: Fuente base para textos
        position: Posición en pantalla (Coordinate)
        width: Ancho del panel de segmentos
    """
    
    # Colores
    BG_COLOR = (20, 20, 20, 200)
    HEADER_COLOR = (255, 100, 0, 255)  # Naranja Strava
    TEXT_COLOR = (255, 255, 255, 255)
    HIGHLIGHT_COLOR = (255, 200, 0, 255)  # Amarillo para tu posición
    ROW_BG_1 = (40, 40, 40, 180)
    ROW_BG_2 = (30, 30, 30, 180)
    
    def __init__(
        self,
        segment_data_file: Path,
        entry_provider: Callable[[], Entry],
        font,
        position: Coordinate = Coordinate(20, 20),
        width: int = 350,
        mode: str = "normal"  # "normal" o "individual"
    ):
        self.entry_provider = entry_provider
        self.font = font
        self.position = position
        self.width = width
        self.mode = mode  # individual = un video por segmento con animaciones extra
        
        # Cargar datos de segmentos
        self.segments: List[Dict[str, Any]] = []
        self._load_segments(segment_data_file)
        
        # Estado actual
        self.current_segment_idx: Optional[int] = None
        self.animation_progress: float = 0.0  # 0.0 - 1.0 para animaciones
        self.completion_shown: set = set()  # Segments already completed
        
        # Cache de fuentes por tamaño
        self._fonts: Dict[int, Any] = {}
        
        # Dimensiones calculadas
        self.header_height = 50 if mode == "individual" else 45
        self.row_height = 32 if mode == "individual" else 28
        self.padding = 15 if mode == "individual" else 10
        
        # Animación de entrada en modo individual
        self.intro_animation_duration = 3.0  # segundos para animación de entrada
    
    def _get_font(self, size: int):
        """Obtiene fuente con caching"""
        if size not in self._fonts:
            self._fonts[size] = self.font.font_variant(size=size)
        return self._fonts[size]
    
    def _load_segments(self, file_path: Path):
        """Carga segmentos desde JSON"""
        if not file_path.exists():
            return
        
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        for seg in data.get('segments', []):
            self.segments.append({
                'id': seg['id'],
                'name': seg['name'],
                'preview_time': datetime.fromisoformat(seg['preview_time']),
                'start_time': datetime.fromisoformat(seg['start_time']),
                'end_time': datetime.fromisoformat(seg['end_time']),
                'leaderboard': seg.get('leaderboard', []),
                'my_position': seg.get('my_position'),
                'my_time': seg.get('my_time'),
                'my_speed': seg.get('my_speed'),
            })
        
        # Ordenar por preview_time
        self.segments.sort(key=lambda x: x['preview_time'])
    
    def _get_current_state(self) -> Tuple[Optional[Dict], SegmentState, float]:
        """
        Determina qué segmento mostrar y en qué estado.
        Retorna: (segmento, estado, progreso_animación)
        """
        entry = self.entry_provider()
        if entry is None or not hasattr(entry, 'dt'):
            return None, SegmentState.HIDDEN, 0.0
        
        current_time = entry.dt
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)
        
        # Buscar segmento activo o en preview
        for i, seg in enumerate(self.segments):
            preview_time = seg['preview_time']
            start_time = seg['start_time']
            end_time = seg['end_time']
            
            # Asegurar timezone aware
            if preview_time.tzinfo is None:
                preview_time = preview_time.replace(tzinfo=timezone.utc)
            if start_time.tzinfo is None:
                start_time = start_time.replace(tzinfo=timezone.utc)
            if end_time.tzinfo is None:
                end_time = end_time.replace(tzinfo=timezone.utc)
            
            seg_id = seg['id']
            
            # Check preview window (100m antes)
            if preview_time <= current_time < start_time:
                # Animación de entrada
                total_preview = (start_time - preview_time).total_seconds()
                elapsed = (current_time - preview_time).total_seconds()
                progress = min(1.0, elapsed / max(total_preview, 2.0))  # Min 2s para animación
                return seg, SegmentState.PREVIEW, progress
            
            # Check active window
            if start_time <= current_time < end_time:
                progress = 0.5 + 0.5 * ((current_time - start_time).total_seconds() / 
                                       max((end_time - start_time).total_seconds(), 1.0))
                return seg, SegmentState.ACTIVE, progress
            
            # Check just completed (3 segundos después)
            if end_time <= current_time < end_time + 3:
                if seg_id not in self.completion_shown:
                    progress = (current_time - end_time).total_seconds() / 3.0
                    return seg, SegmentState.COMPLETED, progress
        
        return None, SegmentState.HIDDEN, 0.0
    
    def _calculate_dimensions(self, segment: Dict, state: SegmentState) -> Tuple[int, int]:
        """Calcula dimensiones del panel según estado"""
        if state == SegmentState.PREVIEW:
            # Solo mostrar nombre del segmento
            return self.width, self.header_height + 20
        
        if state == SegmentState.ACTIVE:
            # Full leaderboard (top 10 + tu posición si no está)
            leaderboard = segment.get('leaderboard', [])
            my_pos = segment.get('my_position')
            
            # Contar filas
            rows = min(len(leaderboard), 10)
            if my_pos and my_pos > 10:
                rows += 1  # Fila extra para tu posición
            
            height = self.header_height + (rows * self.row_height) + self.padding
            return self.width, height
        
        if state == SegmentState.COMPLETED:
            # Resumen compacto
            return self.width, 100
        
        return 0, 0
    
    def _draw_intro(self, draw: ImageDraw, segment: Dict, progress: float, width: int, height: int):
        """Dibuja animación de entrada para modo individual"""
        # Fondo con fade in
        bg_alpha = int(255 * min(1.0, progress * 2))
        bg_color = (*self.BG_COLOR[:3], bg_alpha)
        
        # Escala de animación (zoom in)
        scale = 0.5 + (0.5 * progress)
        
        # Centro del panel
        center_x = width // 2
        center_y = height // 2
        
        # Calcular rectángulo escalado
        w = int(width * scale)
        h = int(height * scale)
        x1 = center_x - w // 2
        y1 = center_y - h // 2
        
        # Fondo
        draw.rounded_rectangle([(x1, y1), (x1 + w, y1 + h)], radius=12, fill=bg_color)
        
        # Header con slide down
        header_slide = int((1 - progress) * -30)
        header_y = y1 + header_slide
        header_color = (*self.HEADER_COLOR[:3], bg_alpha)
        draw.rectangle([(x1, header_y), (x1 + w, header_y + self.header_height)], 
                      fill=header_color)
        
        # Texto "Se aproxima el segmento"
        font_title = self._get_font(16)
        title_text = "Se aproxima el segmento"
        bbox = font_title.getbbox(title_text)
        title_x = x1 + (w - (bbox[2] - bbox[0])) // 2
        title_y = header_y + 8
        draw.text((title_x, title_y), title_text, font=font_title, 
                 fill=(*self.TEXT_COLOR[:3], bg_alpha))
        
        # Nombre del segmento (aparece con delay)
        if progress > 0.3:
            name_progress = min(1.0, (progress - 0.3) / 0.7)
            name_alpha = int(255 * name_progress)
            name = segment.get('name', 'Segmento')
            font_name = self._get_font(24 if len(name) < 25 else 20)
            
            # Truncar si es muy largo
            max_w = w - 40
            bbox = font_name.getbbox(name)
            while bbox[2] > max_w and len(name) > 10:
                name = name[:-4] + "..."
                bbox = font_name.getbbox(name)
            
            name_x = x1 + (w - (bbox[2] - bbox[0])) // 2
            name_y = y1 + self.header_height + 60
            
            # Sombra para el texto
            shadow_offset = 2
            draw.text((name_x + shadow_offset, name_y + shadow_offset), name, 
                     font=font_name, fill=(0, 0, 0, name_alpha // 2))
            # Texto principal
            draw.text((name_x, name_y), name, font=font_name, 
                     fill=(*self.HIGHLIGHT_COLOR[:3], name_alpha))
            
            # Flecha animada indicando abajo
            if progress > 0.6:
                arrow_bounce = int((progress - 0.6) * 20) % 10
                arrow_y = name_y + 50 + arrow_bounce
                font_arrow = self._get_font(30)
                arrow_x = x1 + w // 2 - 15
                draw.text((arrow_x, arrow_y), "▼", font=font_arrow, 
                         fill=(*self.TEXT_COLOR[:3], name_alpha))
    
    def _draw_preview(self, draw: ImageDraw, segment: Dict, progress: float, width: int, height: int):
        """Dibuja estado de preview - animación de entrada con nombre del segmento"""
        # En modo individual, usar intro animado
        if self.mode == "individual":
            self._draw_intro(draw, segment, progress, width, height)
            return
        
        # Modo normal: preview simple
        slide_offset = int((1 - progress) * -50)
        header_rect = (0, slide_offset, width, self.header_height + slide_offset)
        draw.rectangle(header_rect, fill=self.HEADER_COLOR)
        
        name = segment.get('name', 'Segmento')
        font = self._get_font(20)
        max_width = width - 20
        bbox = font.getbbox(name)
        while bbox[2] > max_width and len(name) > 10:
            name = name[:-4] + "..."
            bbox = font.getbbox(name)
        
        text_y = slide_offset + (self.header_height - (bbox[3] - bbox[1])) // 2
        draw.text((10, text_y), name, font=font, fill=self.TEXT_COLOR)
        
        font_small = self._get_font(12)
        draw.text((10, slide_offset + self.header_height + 5), 
                  "> Próximo segmento", font=font_small, fill=self.TEXT_COLOR)
    
    def _draw_active(self, draw: ImageDraw, segment: Dict, progress: float, width: int, height: int):
        """Dibuja estado activo - leaderboard completo"""
        # Background
        draw.rounded_rectangle([(0, 0), (width, height)], radius=8, fill=self.BG_COLOR)
        
        # Header
        header_rect = (0, 0, width, self.header_height)
        draw.rectangle(header_rect, fill=self.HEADER_COLOR)
        
        # Nombre del segmento
        name = segment.get('name', 'Segmento')[:35]
        font_header = self._get_font(18)
        draw.text((10, 12), name, font=font_header, fill=self.TEXT_COLOR)
        
        # Leaderboard
        leaderboard = segment.get('leaderboard', [])
        my_pos = segment.get('my_position')
        my_time = segment.get('my_time', '')
        my_speed = segment.get('my_speed', '')
        
        font_row = self._get_font(14)
        y = self.header_height + 5
        
        # Column headers - ajustar según modo
        if self.mode == "individual":
            # Modo individual: mostrar N°, Nombre, Fecha, Vel, Tiempo
            draw.text((10, y), "N°", font=font_row, fill=(180, 180, 180))
            draw.text((45, y), "Nombre", font=font_row, fill=(180, 180, 180))
            draw.text((width // 2 + 20, y), "Fecha", font=font_row, fill=(180, 180, 180))
            draw.text((width - 100, y), "Km/h", font=font_row, fill=(180, 180, 180))
            draw.text((width - 50, y), "Tiempo", font=font_row, fill=(180, 180, 180))
        else:
            # Modo normal: N°, Nombre, Vel, Tiempo
            draw.text((10, y), "#", font=font_row, fill=(180, 180, 180))
            draw.text((35, y), "Nombre", font=font_row, fill=(180, 180, 180))
            draw.text((width - 70, y), "Vel", font=font_row, fill=(180, 180, 180))
            draw.text((width - 35, y), "Tiempo", font=font_row, fill=(180, 180, 180))
        y += self.row_height
        
        # Mostrar top 10
        shown_positions = set()
        for i, entry in enumerate(leaderboard[:10]):
            rank = entry.get('rank', str(i + 1))
            name = entry.get('name', '')[:15]
            speed = entry.get('speed_kmh', '')
            time_str = entry.get('time', '')
            
            shown_positions.add(int(rank) if rank.isdigit() else i + 1)
            
            # Fila alternada
            row_bg = self.ROW_BG_1 if i % 2 == 0 else self.ROW_BG_2
            if int(rank) == my_pos:
                row_bg = (60, 50, 30, 200)  # Resaltar tu fila
            
            draw.rectangle([(5, y), (width - 5, y + self.row_height - 2)], fill=row_bg)
            
            # Texto
            color = self.HIGHLIGHT_COLOR if int(rank) == my_pos else self.TEXT_COLOR
            draw.text((10, y + 4), rank, font=font_row, fill=color)
            draw.text((35, y + 4), name, font=font_row, fill=color)
            draw.text((width - 70, y + 4), speed, font=font_row, fill=color)
            draw.text((width - 35, y + 4), time_str, font=font_row, fill=color)
            
            y += self.row_height
        
        # Si tu posición no está en el top 10, agregarla al final
        if my_pos and my_pos > 10:
            y += 5
            draw.line([(10, y), (width - 10, y)], fill=(100, 100, 100), width=1)
            y += 8
            
            # Tu posición
            name = "Tú"
            draw.rectangle([(5, y), (width - 5, y + self.row_height - 2)], 
                         fill=(80, 60, 20, 220))
            draw.text((10, y + 4), str(my_pos), font=font_row, fill=self.HIGHLIGHT_COLOR)
            draw.text((35, y + 4), name, font=font_row, fill=self.HIGHLIGHT_COLOR)
            draw.text((width - 70, y + 4), my_speed, font=font_row, fill=self.HIGHLIGHT_COLOR)
            draw.text((width - 35, y + 4), my_time, font=font_row, fill=self.HIGHLIGHT_COLOR)
    
    def _draw_completed(self, draw: ImageDraw, segment: Dict, progress: float, width: int, height: int):
        """Dibuja estado completado - resumen final"""
        # Fade out según progreso
        alpha = int(255 * (1 - progress))
        bg = (*self.BG_COLOR[:3], int(self.BG_COLOR[3] * (1 - progress)))
        
        draw.rounded_rectangle([(0, 0), (width, height)], radius=8, fill=bg)
        
        # Header
        header_color = (*self.HEADER_COLOR[:3], alpha)
        draw.rectangle([(0, 0), (width, 35)], fill=header_color)
        
        # Texto
        font_header = self._get_font(16)
        draw.text((10, 8), "✓ Segmento completado", font=font_header, 
                  fill=(*self.TEXT_COLOR[:3], alpha))
        
        # Resultado
        name = segment.get('name', '')[:30]
        my_pos = segment.get('my_position', '-')
        my_time = segment.get('my_time', '-')
        
        font_result = self._get_font(18)
        font_info = self._get_font(14)
        
        y = 45
        draw.text((10, y), name, font=font_info, fill=(*self.TEXT_COLOR[:3], alpha))
        y += 25
        
        # Tu resultado destacado
        result_text = f"Tu posición: #{my_pos} - {my_time}"
        draw.text((10, y), result_text, font=font_result, fill=self.HIGHLIGHT_COLOR)
    
    def draw(self, image: Image, draw: ImageDraw):
        """Método principal de dibujo"""
        segment, state, progress = self._get_current_state()
        
        if state == SegmentState.HIDDEN or segment is None:
            return
        
        # Calcular dimensiones
        width, height = self._calculate_dimensions(segment, state)
        if width == 0 or height == 0:
            return
        
        # Crear canvas temporal para este widget
        canvas = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        canvas_draw = ImageDraw.Draw(canvas)
        
        # Dibujar según estado
        if state == SegmentState.PREVIEW:
            self._draw_preview(canvas_draw, segment, progress, width, height)
        elif state == SegmentState.ACTIVE:
            self._draw_active(canvas_draw, segment, progress, width, height)
        elif state == SegmentState.COMPLETED:
            self._draw_completed(canvas_draw, segment, progress, width, height)
            # Marcar como mostrado si terminó
            if progress >= 1.0:
                self.completion_shown.add(segment['id'])
        
        # Componer en la imagen principal
        image.alpha_composite(canvas, self.position.tuple())
