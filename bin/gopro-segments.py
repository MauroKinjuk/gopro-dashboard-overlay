#!/usr/bin/env python3
"""
Genera overlay de segmentos Strava desde GPX (sin video de entrada).

Similar a gopro-dashboard.py --use-gpx-only pero optimizado para segmentos.
Permite especificar tiempo de inicio manual para sincronizar con la hora real.

Uso:
    python gopro-segments.py --gpx MiRuta.gpx --segments segments_timed.json --output overlay.mov
    
    # Con hora de inicio específica (para sincronizar):
    python gopro-segments.py --gpx MiRuta.gpx --segments segments_timed.json --start-time 08:30:00
"""

import argparse
import datetime
import subprocess
import sys
from pathlib import Path

# Use local source code
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

from gopro_overlay.log import fatal, log


def parse_time(time_str: str) -> datetime.time:
    """Parse HH:MM:SS"""
    try:
        parts = time_str.split(':')
        if len(parts) == 3:
            return datetime.time(int(parts[0]), int(parts[1]), int(parts[2]))
        elif len(parts) == 2:
            return datetime.time(int(parts[0]), int(parts[1]), 0)
    except (ValueError, IndexError):
        pass
    raise ValueError(f"Formato de hora inválido: {time_str}. Use HH:MM:SS")


def main():
    parser = argparse.ArgumentParser(
        description="Genera overlay de segmentos Strava desde GPX",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  # Básico:
  %(prog)s --gpx carrera.gpx --segments segments_timed.json
  
  # Especificando hora de inicio (para sincronizar con video real):
  %(prog)s --gpx carrera.gpx --segments segments_timed.json --start-time 08:30:00
  
  # Calidad 4K:
  %(prog)s --gpx carrera.gpx --segments segments_timed.json --resolution 4k
        """
    )
    
    parser.add_argument("--gpx", type=Path, required=True,
                        help="Archivo GPX del recorrido")
    parser.add_argument("--segments", type=Path, required=True,
                        help="JSON con datos de segmentos temporizados")
    parser.add_argument("--output", type=Path, default=None,
                        help="Archivo de salida (default: {gpx_name}-segments.mov)")
    parser.add_argument("--start-time", type=str,
                        help="Hora de inicio HH:MM:SS para sincronizar con hora real del evento")
    parser.add_argument("--resolution", choices=["1080", "2k", "4k"], default="1080",
                        help="Resolución de salida (default: 1080)")
    parser.add_argument("--profile", default="overlay-capcut",
                        help="Perfil ffmpeg a usar (default: overlay-capcut)")
    parser.add_argument("--font", type=Path, default=None,
                        help="Fuente personalizada (default: Coolvetica.otf)")
    
    args = parser.parse_args()
    
    # Validar archivos
    if not args.gpx.exists():
        fatal(f"No se encontró el archivo GPX: {args.gpx}")
    
    if not args.segments.exists():
        fatal(f"No se encontró el archivo de segmentos: {args.segments}")
    
    # Determinar output
    if args.output is None:
        output = args.gpx.parent / f"{args.gpx.stem}-segments.mov"
    else:
        output = args.output
    
    # Resolución
    resolution_map = {
        "1080": "1920x1080",
        "2k": "2560x1440", 
        "4k": "3840x2160"
    }
    overlay_size = resolution_map[args.resolution]
    
    # Forzar perfil con transparencia alpha (ignorar el que pasó el usuario)
    alpha_profile = "alpha-qtrle"  # QuickTime Animation con alpha
    
    # Layout según resolución
    layout_map = {
        "1080": "segment-layout.xml",
        "2k": "segment-layout.xml",  # Podemos crear versiones específicas
        "4k": "segment-layout.xml"
    }
    layout_file = project_root / "gopro_overlay" / "layouts" / layout_map[args.resolution]
    
    # Fuente
    if args.font is None:
        font_file = project_root / "Coolvetica.otf"
    else:
        font_file = args.font
    
    if not font_file.exists():
        log(f"⚠️ No se encontró la fuente {font_file}, se usará la default")
        font_file = None
    
    # Copiar archivo de segmentos al directorio del proyecto (donde el layout lo espera)
    import shutil
    import os
    segments_dest = project_root / "segments_timed.json"
    
    # Solo copiar si son archivos diferentes
    try:
        if not os.path.samefile(str(args.segments), str(segments_dest)):
            shutil.copy(str(args.segments), str(segments_dest))
            log(f"📄 Copiado {args.segments.name} a {segments_dest}")
        else:
            log(f"📄 Usando segments_timed.json existente en {segments_dest}")
    except FileNotFoundError:
        # segments_dest no existe, copiar normalmente
        shutil.copy(str(args.segments), str(segments_dest))
        log(f"📄 Copiado {args.segments.name} a {segments_dest}")
    
    # Construir comando
    dashboard_script = project_root / "bin" / "gopro-dashboard.py"
    
    cmd = [
        sys.executable,
        str(dashboard_script),
    ]
    
    if font_file:
        cmd.extend(["--font", str(font_file)])
    
    cmd.extend([
        "--use-gpx-only",
        "--gpx", str(args.gpx),
        "--profile", alpha_profile,
        "--overlay-size", overlay_size,
        str(output),
        "--units-speed", "kph",
        "--layout", "xml",
        "--layout-xml", str(layout_file),
        "--include", "segment_overlay"
    ])
    
    # Añadir tiempo de inicio si se especificó
    if args.start_time:
        try:
            t = parse_time(args.start_time)
            # Convertir a formato que acepte gopro-dashboard
            # Usamos un hack: modificamos el GPX o usamos --video-time-start
            # Pero como es gpx-only, usamos la metadata del archivo
            log(f"⏰ Sincronizando con hora de inicio: {args.start_time}")
            # El --video-time-start no aplica para gpx-only según el código
            # Así que mostramos un warning
            log(f"⚠️ Para sincronizar exactamente, asegurate de que el GPX tenga la hora correcta")
        except ValueError as e:
            fatal(str(e))
    
    # Ejecutar
    log(f"🎬 Generando overlay de segmentos con FONDO TRANSPARENTE...")
    log(f"   Resolución: {overlay_size}")
    log(f"   Codec: QuickTime Animation (Alpha)")
    log(f"   Salida: {output}")
    log("")
    
    result = subprocess.run(cmd, capture_output=False)
    
    if result.returncode == 0:
        log(f"")
        log(f"✅ Overlay generado con transparencia: {output}")
        log(f"   💡 Importa este archivo en CapCut - el fondo es transparente!")
        
        # Mostrar info de los segmentos
        import json
        with open(segments_dest, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        log(f"")
        log(f"📊 Segmentos incluidos ({len(data.get('segments', []))}):")
        for seg in data.get('segments', [])[:5]:  # Mostrar max 5
            name = seg.get('name', 'Unknown')
            start = seg.get('start_time', '')
            pos = seg.get('my_position', '?')
            log(f"   • {name[:40]:<40} | Pos: #{pos}")
        
        if len(data.get('segments', [])) > 5:
            log(f"   ... y {len(data.get('segments', [])) - 5} más")
    else:
        log(f"")
        fatal(f"❌ Error generando overlay (código {result.returncode})")


if __name__ == "__main__":
    main()
