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
    # Datos de Strava API para distancia exacta
    start_index: Optional[int] = None  # Índice en el stream de distancia de Strava
    strava_start_distance_km: Optional[float] = None  # Distancia acumulada exacta de Strava
    # Stats del segmento scrapeadas de la pagina de Strava
    distance_km: Optional[float] = None
    elevation_gain_m: Optional[float] = None
    avg_grade_pct: Optional[float] = None
    total_athletes: Optional[int] = None
    total_efforts: Optional[int] = None


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
    # Distancia acumulada desde el inicio del recorrido hasta el inicio del segmento (km)
    start_distance_km: Optional[float] = None
    # Stats del segmento (opcionales, scrapeados de Strava)
    distance_km: Optional[float] = None
    elevation_gain_m: Optional[float] = None
    avg_grade_pct: Optional[float] = None
    total_athletes: Optional[int] = None
    total_efforts: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "preview_time": self.preview_time.isoformat(),
            "start_point": {"lat": self.start_point.lat, "lon": self.start_point.lon},
            "end_point": {"lat": self.end_point.lat, "lon": self.end_point.lon},
            "start_distance_km": self.start_distance_km,
            "leaderboard": self.leaderboard,
            "my_position": self.my_position,
            "my_time": self.my_time,
            "my_speed": self.my_speed,
            "stats": {
                "distance_km": self.distance_km,
                "elevation_gain_m": self.elevation_gain_m,
                "avg_grade_pct": self.avg_grade_pct,
                "total_athletes": self.total_athletes,
                "total_efforts": self.total_efforts,
            },
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
        Busca TODAS las ocurrencias posibles y retorna la primera (más cercana al inicio).
        Esto es importante para circuitos donde se pasa múltiples veces por el mismo segmento.
        """
        if len(self.gpx_points) < 2:
            return None
        
        start_pt = Point(lat=segment.start_lat, lon=segment.start_lon)
        end_pt = Point(lat=segment.end_lat, lon=segment.end_lon)
        
        TOLERANCE_METERS = 500  # Tolerancia para coincidencia de coordenadas
        MIN_SEGMENT_DURATION_SECONDS = 30  # Mínimo tiempo entre inicio y fin del segmento
        
        # Buscar TODAS las ocurrencias válidas del segmento
        occurrences = []
        
        # Recorrer el GPX buscando puntos de inicio candidatos
        for start_idx in range(len(self.gpx_points)):
            start_time_gpx, start_point_gpx = self.gpx_points[start_idx]
            
            # Verificar si este punto está cerca del inicio del segmento
            dist_to_start = haversine_metres(
                start_pt.lat, start_pt.lon,
                start_point_gpx.lat, start_point_gpx.lon
            )
            
            if dist_to_start > TOLERANCE_METERS:
                continue
            
            # Buscar punto de fin después del inicio
            for end_idx in range(start_idx + 1, len(self.gpx_points)):
                end_time_gpx, end_point_gpx = self.gpx_points[end_idx]
                
                # Verificar distancia al punto de fin del segmento
                dist_to_end = haversine_metres(
                    end_pt.lat, end_pt.lon,
                    end_point_gpx.lat, end_point_gpx.lon
                )
                
                if dist_to_end <= TOLERANCE_METERS:
                    # Verificar duración mínima (evitar match espurios)
                    duration_seconds = (end_time_gpx - start_time_gpx).total_seconds()
                    if duration_seconds >= MIN_SEGMENT_DURATION_SECONDS:
                        occurrences.append({
                            'start_idx': start_idx,
                            'end_idx': end_idx,
                            'start_time': start_time_gpx,
                            'end_time': end_time_gpx,
                            'dist_to_start': dist_to_start,
                            'dist_to_end': dist_to_end,
                        })
                    break  # Tomar el primer fin válido después del inicio
        
        if not occurrences:
            return None
        
        # Elegir la primera ocurrencia (la más cercana al inicio del recorrido)
        # Ordenar por start_idx (posición en el GPX) y tomar el primero
        occurrences.sort(key=lambda x: x['start_idx'])
        best = occurrences[0]
        
        # Log informativo si hay múltiples ocurrencias
        if len(occurrences) > 1:
            dist_km_first = best['start_idx'] * 0.01  # Aproximación rápida
            print(f"   🔄 Segmento '{segment.name}' tiene {len(occurrences)} ocurrencias - usando la primera (~{dist_km_first:.1f}km)")
        
        start_idx = best['start_idx']
        end_idx = best['end_idx']
        start_time = best['start_time']
        end_time = best['end_time']
        
        # Calcular distancia acumulada desde el inicio del recorrido hasta el inicio del segmento
        # Usar el valor de Strava si está disponible (más preciso)
        if segment.strava_start_distance_km is not None:
            start_distance_km = segment.strava_start_distance_km
            print(f"   ✅ Usando distancia de Strava: {start_distance_km:.2f} km")
        else:
            # Calcular desde el GPX
            start_distance_km = 0.0
            if start_idx > 0:
                for i in range(start_idx):
                    if i + 1 < len(self.gpx_points):
                        pt_current = self.gpx_points[i][1]
                        pt_next = self.gpx_points[i + 1][1]
                        start_distance_km += haversine_metres(
                            pt_current.lat, pt_current.lon,
                            pt_next.lat, pt_next.lon
                        )
                start_distance_km /= 1000.0  # Convertir a km
        
        # Calcular preview_time (100m antes de entrar)
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
            preview_time=preview_time,
            start_distance_km=start_distance_km,
            distance_km=segment.distance_km,
            elevation_gain_m=segment.elevation_gain_m,
            avg_grade_pct=segment.avg_grade_pct,
            total_athletes=segment.total_athletes,
            total_efforts=segment.total_efforts,
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


def load_segment_meta(csv_path: Path) -> Dict[str, Dict[str, Any]]:
    """
    Carga segment_meta.csv generado por segments_scraper.py.
    Retorna dict: segment_id -> {distance_km, elevation_gain_m, avg_grade_pct,
                                 total_athletes, total_efforts}
    """
    import csv
    result: Dict[str, Dict[str, Any]] = {}
    if not csv_path.exists():
        return result

    def _f(s: str) -> Optional[float]:
        if not s or not s.strip():
            return None
        try:
            return float(s.strip().replace(",", "."))
        except Exception:
            return None

    def _i(s: str) -> Optional[int]:
        v = _f(s)
        return int(v) if v is not None else None

    try:
        with open(csv_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                seg_id = (row.get('SegmentID') or '').strip()
                if not seg_id:
                    continue
                result[seg_id] = {
                    'distance_km':      _f(row.get('DistanceKm', '')),
                    'elevation_gain_m': _f(row.get('ElevationGainM', '')),
                    'avg_grade_pct':    _f(row.get('AvgGradePct', '')),
                    'total_athletes':   _i(row.get('TotalAthletes', '')),
                    'total_efforts':    _i(row.get('TotalEfforts', '')),
                }
    except Exception:
        pass
    return result


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
    preview_distance_m: float = 100.0,
    distance_stream_file: Optional[Path] = None,
    segment_efforts_file: Optional[Path] = None
) -> List[TimedSegment]:
    """
    Construye el dataset completo de segmentos temporizados.
    
    Args:
        gpx_file: Archivo GPX del recorrido
        segments_json: JSON con datos básicos de segmentos (de Strava API)
        leaderboards_dir: Directorio con CSVs de leaderboards
        output_file: Archivo JSON de salida
        preview_distance_m: Distancia de anticipación para mostrar overlay
        distance_stream_file: JSON con stream de distancia de Strava (opcional)
        segment_efforts_file: JSON con segment efforts y start_index (opcional)
    """
    # Cargar stream de distancia de Strava si está disponible
    distance_stream: Optional[List[float]] = None
    if distance_stream_file and distance_stream_file.exists():
        try:
            with open(distance_stream_file, 'r', encoding='utf-8') as f:
                distance_stream = json.load(f)
            print(f"   📊 Stream de distancia de Strava: {len(distance_stream)} puntos")
        except Exception as e:
            print(f"   ⚠️ Error cargando stream de distancia: {e}")
    
    # Cargar segment efforts con índices si están disponibles
    segment_efforts: Dict[str, Dict] = {}
    if segment_efforts_file and segment_efforts_file.exists():
        try:
            with open(segment_efforts_file, 'r', encoding='utf-8') as f:
                segment_efforts = json.load(f)
            print(f"   🎯 Segment efforts de Strava: {len(segment_efforts)} segmentos")
        except Exception as e:
            print(f"   ⚠️ Error cargando segment efforts: {e}")
    # Cargar segmentos base
    with open(segments_json, 'r', encoding='utf-8') as f:
        raw_segments = json.load(f)
    
    # Cargar leaderboards
    leaderboards = {}
    for csv_file in leaderboards_dir.glob("leaderboard_*.csv"):
        seg_id = csv_file.stem.replace("leaderboard_", "")
        boards = load_leaderboard_csv(csv_file)
        leaderboards.update(boards)

    # Cargar metadata extra del segmento (distancia, desnivel, pendiente, atletas)
    segment_stats = load_segment_meta(leaderboards_dir / "segment_meta.csv")
    
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
        
        stats = segment_stats.get(seg_id, {})
        
        # Obtener datos de Strava API si están disponibles
        start_index = None
        strava_start_distance_km = None
        
        effort_data = segment_efforts.get(seg_id)
        if effort_data:
            start_index = effort_data.get('start_index')
            # Calcular distancia desde el stream si tenemos ambos
            if distance_stream and start_index is not None:
                if 0 <= start_index < len(distance_stream):
                    strava_start_distance_km = distance_stream[start_index] / 1000.0  # Convertir a km
        
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
            my_speed=my_speed,
            start_index=start_index,
            strava_start_distance_km=strava_start_distance_km,
            distance_km=stats.get('distance_km'),
            elevation_gain_m=stats.get('elevation_gain_m'),
            avg_grade_pct=stats.get('avg_grade_pct'),
            total_athletes=stats.get('total_athletes'),
            total_efforts=stats.get('total_efforts'),
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
