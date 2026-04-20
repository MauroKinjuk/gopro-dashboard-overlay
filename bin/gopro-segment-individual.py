#!/usr/bin/env python3
"""
Genera videos individuales para cada segmento Strava.
Cada video contiene:
- Animación de entrada: "Se aproxima el segmento [Nombre]"
- Leaderboard animado con: Posición, Nombre, Fecha, Velocidad, Tiempo

Uso:
    python bin/gopro-segment-individual.py \
        --gpx carrera.gpx \
        --segments segments_timed.json \
        --output-dir ./segment_videos/ \
        --resolution 1080
"""

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def log(msg):
    print(f"[SEGMENT] {msg}")


def parse_segments_timed(segments_file: Path):
    """Parsea el JSON de segmentos temporizados"""
    with open(segments_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    segments = []
    for seg in data.get('segments', []):
        segments.append({
            'id': seg['id'],
            'name': seg['name'],
            'preview_time': datetime.fromisoformat(seg['preview_time']),
            'start_time': datetime.fromisoformat(seg['start_time']),
            'end_time': datetime.fromisoformat(seg['end_time']),
            'start_distance_km': seg.get('start_distance_km'),
            'leaderboard': seg.get('leaderboard', []),
            'my_position': seg.get('my_position'),
            'my_time': seg.get('my_time'),
            'my_speed': seg.get('my_speed'),
        })
    
    return segments, data.get('gpx_file', '')


def generate_segment_video(segment, gpx_file: Path, output_file: Path, resolution: str, font_file: Path = None):
    """Genera un video individual para un segmento"""
    
    project_root = Path(__file__).parent.parent
    
    # Calcular duración del video (desde 5s antes del preview hasta 3s después del final)
    preview_time = segment['preview_time']
    end_time = segment['end_time']
    
    if preview_time.tzinfo is None:
        preview_time = preview_time.replace(tzinfo=timezone.utc)
    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)
    
    # Video empieza 5 segundos antes del preview para la animación de entrada
    video_start = preview_time.timestamp() - 5
    # Video termina 3 segundos después del segmento
    video_end = end_time.timestamp() + 3
    duration = video_end - video_start
    
    # Calcular tiempo de inicio en formato datetime para --start
    from datetime import datetime
    start_dt = datetime.fromtimestamp(video_start)
    start_str = start_dt.strftime("%Y-%m-%d %H:%M:%S")
    
    # Crear metadata del segmento para este video específico
    segment_data = {
        'gpx_file': str(gpx_file),
        'preview_distance_m': 100,
        'segments': [{
            'id': segment['id'],
            'name': segment['name'],
            'preview_time': segment['preview_time'].isoformat(),
            'start_time': segment['start_time'].isoformat(),
            'end_time': segment['end_time'].isoformat(),
            'start_distance_km': segment.get('start_distance_km'),
            'leaderboard': segment['leaderboard'],
            'my_position': segment['my_position'],
            'my_time': segment['my_time'],
            'my_speed': segment['my_speed'],
        }]
    }
    
    # Guardar JSON temporal
    temp_json = output_file.parent / f"segment_{segment['id']}.json"
    with open(temp_json, 'w', encoding='utf-8') as f:
        json.dump(segment_data, f, indent=2, ensure_ascii=False)
    
    # Layout específico para video individual (más grande, centrado)
    layout_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<layout>
  <component 
    type="segment_overlay" 
    x="200" 
    y="100" 
    file="{temp_json.name}"
    width="800"
    mode="individual"
  />
</layout>'''
    
    temp_layout = output_file.parent / f"layout_{segment['id']}.xml"
    with open(temp_layout, 'w', encoding='utf-8') as f:
        f.write(layout_content)
    
    # Preparar comando
    dashboard_script = project_root / "bin" / "gopro-dashboard.py"
    
    cmd = [
        sys.executable,
        str(dashboard_script),
        "--use-gpx-only",
        str(gpx_file),
        str(output_file),
        "--layout", "xml",
        "--layout-xml", str(temp_layout),
        "--profile", "alpha-qtrle",
        "--start-date", start_str,
        "--duration", str(int(duration)),
    ]
    
    if font_file and font_file.exists():
        cmd.extend(["--font", str(font_file)])
    
    log(f"Generando video para segmento: {segment['name']}")
    log(f"  Duración: {duration:.1f}s | Output: {output_file}")
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    # Limpiar archivos temporales
    temp_json.unlink(missing_ok=True)
    temp_layout.unlink(missing_ok=True)
    
    if result.returncode != 0:
        log(f"Error generando video: {result.stderr}")
        return False
    
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Genera videos individuales para cada segmento Strava"
    )
    parser.add_argument("--gpx", type=Path, required=True, help="Archivo GPX")
    parser.add_argument("--segments", type=Path, required=True, 
                        help="Archivo JSON con datos de segmentos temporizados")
    parser.add_argument("--output-dir", type=Path, default=Path("./segment_videos"),
                        help="Directorio de salida para los videos")
    parser.add_argument("--resolution", choices=["1080", "2k", "4k"], default="1080",
                        help="Resolución de salida")
    parser.add_argument("--font", type=Path, default=None, help="Archivo de fuente personalizada")
    parser.add_argument("--segments-filter", type=str, default=None,
                        help="Filtrar segmentos por nombre (substring)")
    
    args = parser.parse_args()
    
    if not args.gpx.exists():
        log(f"No se encontró el archivo GPX: {args.gpx}")
        sys.exit(1)
    
    if not args.segments.exists():
        log(f"No se encontró el archivo de segmentos: {args.segments}")
        sys.exit(1)
    
    # Crear directorio de salida
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    # Cargar segmentos
    segments, gpx_path = parse_segments_timed(args.segments)
    
    if not segments:
        log("No hay segmentos para procesar")
        sys.exit(1)
    
    log(f"Procesando {len(segments)} segmentos...")
    
    # Filtrar si es necesario
    if args.segments_filter:
        segments = [s for s in segments if args.segments_filter.lower() in s['name'].lower()]
        log(f"Filtrados: {len(segments)} segmentos coinciden con '{args.segments_filter}'")
    
    # Generar video para cada segmento
    success_count = 0
    for i, segment in enumerate(segments, 1):
        # Sanitizar nombre para archivo
        safe_name = "".join(c for c in segment['name'] if c.isalnum() or c in (' ', '-', '_')).rstrip()
        safe_name = safe_name.replace(' ', '_')[:25]  # Reducido para dejar espacio al km
        
        # Obtener distancia de inicio para el nombre del archivo
        start_dist_km = segment.get('start_distance_km')
        if start_dist_km is not None:
            dist_str = f"{start_dist_km:.1f}km"
        else:
            dist_str = "unknown"
        
        output_file = args.output_dir / f"segment_{i:02d}_{dist_str}_{safe_name}.mov"
        
        log(f"\n[{i}/{len(segments)}] {segment['name']} @ {dist_str}")
        
        if generate_segment_video(
            segment=segment,
            gpx_file=args.gpx,
            output_file=output_file,
            resolution=args.resolution,
            font_file=args.font
        ):
            success_count += 1
            log(f"  ✓ Guardado: {output_file}")
        else:
            log(f"  ✗ Falló")
    
    log(f"\n{'='*50}")
    log(f"Completado: {success_count}/{len(segments)} videos generados")
    log(f"Directorio: {args.output_dir.absolute()}")


if __name__ == "__main__":
    main()
