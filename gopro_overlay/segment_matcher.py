"""
Segment Matcher - Vincula segmentos de Strava con timestamps de GPX

Este módulo permite determinar en qué momento del recorrido (GPX) se encuentra
cada segmento de Strava, usando las coordenadas de inicio y fin del segmento.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timezone

import gpxpy
import gpxpy.gpx

from gopro_overlay.point import Point
from gopro_overlay.geo import haversine_metres


@dataclass
class SegmentLeaderboardEntry:
    rank: str
    name: str
    date: str
    speed_kmh: str
    time_str: str


@dataclass
class SegmentData:
    id: str
    name: str
    start_lat: float
    start_lon: float
    end_lat: float
    end_lon: float
    distance_m: float
    leaderboard: List[SegmentLeaderboardEntry]
    my_position: Optional[int] = None
    my_time: Optional[str] = None
    my_speed: Optional[str] = None


@dataclass
class TimedSegment:
    """Segmento con timestamps del GPX"""
    id: str
    name: str
    start_time: datetime
    end_time: datetime
    start_point: Point
    end_point: Point
    leaderboard: List[Dict[str, Any]]
    my_position: Optional[int]
    my_time: Optional[str]
    my_speed: Optional[str]
    preview_time: datetime  # 100m antes de entrar

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "preview_time": self.preview_time.isoformat(),
            "start_point": {"lat": self.start_point.lat, "lon": self.start_point.lon},
            "end_point": {"lat": self.end_point.lat, "lon": self.end_point.lon},
            "leaderboard": self.leaderboard,
            "my_position": self.my_position,
            "my_time": self.my_time,
            "my_speed": self.my_speed,
        }


class SegmentMatcher:
    """
    Encuentra segmentos en un GPX basándose en coordenadas de inicio/fin.
    """
    
    def __init__(self, gpx_file: Path, preview_distance_m: float = 100.0):
        self.gpx_file = gpx_file
        self.preview_distance_m = preview_distance_m
        self.gpx_points: List[Tuple[datetime, Point]] = []
        self._load_gpx()
    
    def _load_gpx(self):
        """Carga puntos del GPX con sus timestamps"""
        with open(self.gpx_file, 'r', encoding='utf-8') as f:
            gpx = gpxpy.parse(f)
        
        for track in gpx.tracks:
            for segment in track.segments:
                for point in segment.points:
                    if point.time:
                        dt = point.time
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        self.gpx_points.append((dt, Point(lat=point.latitude, lon=point.longitude)))
        
        # Ordenar por tiempo
        self.gpx_points.sort(key=lambda x: x[0])
    
    def find_nearest_point(self, target: Point, start_idx: int = 0) -> Tuple[int, float, datetime]:
        """
        Encuentra el punto más cercano al target en el GPX.
        Retorna (index, distance_m, timestamp)
        """
        min_dist = float('inf')
        min_idx = start_idx
        
        for i, (dt, pt) in enumerate(self.gpx_points[start_idx:], start=start_idx):
            dist = haversine_metres(target.lat, target.lon, pt.lat, pt.lon)
            if dist < min_dist:
                min_dist = dist
                min_idx = i
        
        return min_idx, min_dist, self.gpx_points[min_idx][0]
    
    def match_segment(self, segment: SegmentData) -> Optional[TimedSegment]:
        """
        Encuentra el segmento en el GPX y retorna los timestamps.
        Busca primero el punto de inicio, luego el de fin después del inicio.
        """
        if len(self.gpx_points) < 2:
            return None
        
        start_pt = Point(lat=segment.start_lat, lon=segment.start_lon)
        end_pt = Point(lat=segment.end_lat, lon=segment.end_lon)
        
        # Encontrar punto de inicio
        start_idx, start_dist, start_time = self.find_nearest_point(start_pt, 0)
        
        # Si está muy lejos, probablemente no es este recorrido
        if start_dist > 500:  # 500 metros de tolerancia
            return None
        
        # Encontrar punto de fin después del inicio
        _, end_dist, end_time = self.find_nearest_point(end_pt, start_idx)
        
        if end_dist > 500:
            return None
        
        # Calcular preview_time (100m antes de entrar)
        preview_idx = max(0, start_idx - 10)  # Empezar buscando hacia atrás
        preview_time = start_time
        
        for i in range(start_idx - 1, -1, -1):
            pt = self.gpx_points[i][1]
            dist_from_start = haversine_metres(start_pt.lat, start_pt.lon, pt.lat, pt.lon)
            if dist_from_start >= self.preview_distance_m:
                preview_time = self.gpx_points[i][0]
                break
        else:
            # Si no encontramos punto a 100m, usar 10 segundos antes
            preview_time = datetime.fromtimestamp(
                start_time.timestamp() - 10, 
                tz=timezone.utc
            )
        
        return TimedSegment(
            id=segment.id,
            name=segment.name,
            start_time=start_time,
            end_time=end_time,
            start_point=start_pt,
            end_point=end_pt,
            leaderboard=[
                {
                    "rank": e.rank,
                    "name": e.name,
                    "date": e.date,
                    "speed_kmh": e.speed_kmh,
                    "time": e.time_str,
                }
                for e in segment.leaderboard
            ],
            my_position=segment.my_position,
            my_time=segment.my_time,
            my_speed=segment.my_speed,
            preview_time=preview_time
        )
    
    def match_all_segments(self, segments: List[SegmentData]) -> List[TimedSegment]:
        """Match todos los segmentos y ordenar por tiempo de inicio"""
        timed = []
        for seg in segments:
            matched = self.match_segment(seg)
            if matched:
                timed.append(matched)
        
        # Ordenar por tiempo de preview
        timed.sort(key=lambda x: x.preview_time)
        return timed


def load_leaderboard_csv(csv_path: Path) -> Dict[str, List[SegmentLeaderboardEntry]]:
    """
    Carga CSVs de leaderboards generados por segments_scraper.py
    Retorna dict: segment_id -> lista de entradas
    """
    import csv
    
    leaderboards = {}
    
    if not csv_path.exists():
        return leaderboards
    
    with open(csv_path, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            seg_id = row.get('SegmentID', '').strip()
            if not seg_id:
                continue
            
            if seg_id not in leaderboards:
                leaderboards[seg_id] = []
            
            entry = SegmentLeaderboardEntry(
                rank=row.get('Rank', ''),
                name=row.get('Nombre', ''),
                date=row.get('Fecha', ''),
                speed_kmh=row.get('KM/H', ''),
                time_str=row.get('Segundos', '')
            )
            leaderboards[seg_id].append(entry)
    
    return leaderboards


def build_segment_data(
    gpx_file: Path,
    segments_json: Path,
    leaderboards_dir: Path,
    output_file: Path,
    preview_distance_m: float = 100.0
) -> List[TimedSegment]:
    """
    Construye el dataset completo de segmentos temporizados.
    
    Args:
        gpx_file: Archivo GPX del recorrido
        segments_json: JSON con datos básicos de segmentos (de Strava API)
        leaderboards_dir: Directorio con CSVs de leaderboards
        output_file: Archivo JSON de salida
        preview_distance_m: Distancia de anticipación para mostrar overlay
    """
    # Cargar segmentos base
    with open(segments_json, 'r', encoding='utf-8') as f:
        raw_segments = json.load(f)
    
    # Cargar leaderboards
    leaderboards = {}
    for csv_file in leaderboards_dir.glob("leaderboard_*.csv"):
        seg_id = csv_file.stem.replace("leaderboard_", "")
        boards = load_leaderboard_csv(csv_file)
        leaderboards.update(boards)
    
    # Construir objetos SegmentData
    segments = []
    for seg in raw_segments.get('segments', []):
        seg_id = str(seg.get('id', ''))
        
        # Buscar mi posición en los datos
        my_pos = None
        my_time = None
        my_speed = None
        
        for entry in leaderboards.get(seg_id, []):
            if entry.name == "Mauro Kinjuk":  # TODO: hacer configurable
                my_pos = int(entry.rank) if entry.rank.isdigit() else None
                my_time = entry.time_str
                my_speed = entry.speed_kmh
                break
        
        # Si no está en leaderboard, buscar archivo my_rank_*.txt
        my_rank_file = leaderboards_dir / f"my_rank_{seg_id}.txt"
        if my_pos is None and my_rank_file.exists():
            my_pos = int(my_rank_file.read_text().strip())
        
        segment = SegmentData(
            id=seg_id,
            name=seg.get('name', ''),
            start_lat=seg.get('start_lat', 0),
            start_lon=seg.get('start_lon', 0),
            end_lat=seg.get('end_lat', 0),
            end_lon=seg.get('end_lon', 0),
            distance_m=seg.get('distance', 0),
            leaderboard=leaderboards.get(seg_id, []),
            my_position=my_pos,
            my_time=my_time,
            my_speed=my_speed
        )
        segments.append(segment)
    
    # Hacer matching con GPX
    matcher = SegmentMatcher(gpx_file, preview_distance_m)
    timed_segments = matcher.match_all_segments(segments)
    
    # Guardar resultado
    output_data = {
        "gpx_file": str(gpx_file),
        "preview_distance_m": preview_distance_m,
        "segments": [s.to_dict() for s in timed_segments]
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    return timed_segments


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Match Strava segments with GPX timestamps")
    parser.add_argument("--gpx", type=Path, required=True, help="Archivo GPX del recorrido")
    parser.add_argument("--segments", type=Path, required=True, help="JSON con datos de segmentos")
    parser.add_argument("--leaderboards", type=Path, required=True, help="Directorio con CSVs de leaderboards")
    parser.add_argument("--output", type=Path, required=True, help="Archivo JSON de salida")
    parser.add_argument("--preview-distance", type=float, default=100.0, help="Distancia de anticipación (m)")
    
    args = parser.parse_args()
    
    timed = build_segment_data(
        gpx_file=args.gpx,
        segments_json=args.segments,
        leaderboards_dir=args.leaderboards,
        output_file=args.output,
        preview_distance_m=args.preview_distance
    )
    
    print(f"✅ Matched {len(timed)} segments")
    for seg in timed:
        print(f"  - {seg.name}: {seg.start_time.strftime('%H:%M:%S')} - {seg.end_time.strftime('%H:%M:%S')} "
              f"(preview: {seg.preview_time.strftime('%H:%M:%S')})")
