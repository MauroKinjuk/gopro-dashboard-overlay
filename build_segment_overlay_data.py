#!/usr/bin/env python3
"""
Script orquestador para preparar datos de segmentos Strava para overlay en videos.

Este script coordina:
1. segments_retriever.py - Obtiene segmentos de la API de Strava
2. segments_scraper.py - Obtiene leaderboards de la web de Strava  
3. segment_matcher.py - Vincula segmentos con timestamps del GPX

Uso:
    python build_segment_overlay_data.py \
        --gpx MiCarrera.gpx \
        --activity-url https://www.strava.com/activities/12345678 \
        --output segments_timed.json

O pasando los datos manualmente si ya los tenés:
    python build_segment_overlay_data.py \
        --gpx MiCarrera.gpx \
        --segments-file segments.json \
        --leaderboards-dir leaderboards/ \
        --output segments_timed.json
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

# Asegurar que el path del proyecto esté disponible
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from gopro_overlay.segment_matcher import build_segment_data


def run_segments_retriever(activity_url: str, output_file: Path) -> bool:
    """
    Ejecuta segments_retriever.py para obtener segmentos de la API de Strava.
    """
    # Strava-Scraper-Leaderboard está en el directorio padre (sibling project)
    # Se puede sobrescribir con la variable de entorno STRAVA_PROJECT_PATH
    import os
    env_path = os.environ.get('STRAVA_PROJECT_PATH')
    if env_path:
        STRAVA_PROJECT = Path(env_path)
    else:
        STRAVA_PROJECT = PROJECT_ROOT.parent / "Strava-Scraper-Leaderboard"
    retriever_script = STRAVA_PROJECT / "segments_retriever.py"
    
    if not retriever_script.exists():
        print(f"⚠️ No se encontró {retriever_script}")
        print("   Usando datos manuales de segmentos...")
        return False
    
    print(f"🔍 Obteniendo segmentos de: {activity_url}")
    
    # Modificar el script temporalmente para usar la URL proporcionada
    # (el script original tiene la URL hardcodeada)
    script_content = retriever_script.read_text(encoding='utf-8')
    
    # Reemplazar la URL usando regex (más flexible)
    import re
    original_url_pattern = r'(ACTIVITY_URL\s*=\s*)"[^"]+"'
    new_url_line = f'ACTIVITY_URL = "{activity_url}"'
    
    original_match = re.search(original_url_pattern, script_content)
    if original_match:
        original_url_line = original_match.group(0)
        script_content = re.sub(original_url_pattern, new_url_line, script_content)
        retriever_script.write_text(script_content, encoding='utf-8')
    
    try:
        # Ejecutar el script
        result = subprocess.run(
            [sys.executable, str(retriever_script)],
            capture_output=True,
            text=True,
            cwd=str(retriever_script.parent)
        )
        
        if result.returncode == 0:
            print("✅ Segmentos obtenidos correctamente")
            # Mostrar output del script para debugging
            if result.stdout:
                print(f"   Output: {result.stdout[:200]}...")
            # Mover segments.csv al directorio de trabajo
            source_csv = retriever_script.parent / "segments.csv"
            if source_csv.exists():
                import shutil
                target_csv = output_file.parent / "segments_from_api.csv"
                shutil.copy(str(source_csv), str(target_csv))
                print(f"📄 Guardado en: {target_csv}")
                return True
            else:
                print(f"⚠️ No se encontró segments.csv después de ejecutar el retriever")
                return False
        else:
            print(f"[ERROR] Error obteniendo segmentos (código {result.returncode}):")
            if result.stderr:
                print(f"   stderr: {result.stderr}")
            if result.stdout:
                print(f"   stdout: {result.stdout}")
            return False
            
    finally:
        # Restaurar URL original
        if original_match:
            script_content = re.sub(original_url_pattern, original_url_line, script_content)
            retriever_script.write_text(script_content, encoding='utf-8')
    
    return False


def run_segments_scraper(segments_csv: Path, output_dir: Path) -> bool:
    """
    Ejecuta segments_scraper.py para obtener leaderboards de cada segmento.
    """
    STRAVA_PROJECT = PROJECT_ROOT.parent / "Strava-Scraper-Leaderboard"
    scraper_script = STRAVA_PROJECT / "segments_scraper.py"
    
    if not scraper_script.exists():
        print(f"⚠️ No se encontró {scraper_script}")
        return False
    
    print("🏆 Obteniendo leaderboards de Strava (scraping)...")
    
    # Copiar CSV al directorio del scraper
    import shutil
    target_csv = scraper_script.parent / "segments.csv"
    shutil.copy(str(segments_csv), str(target_csv))
    
    try:
        result = subprocess.run(
            [sys.executable, str(scraper_script)],
            capture_output=True,
            text=True,
            cwd=str(scraper_script.parent)
        )
        
        if result.returncode == 0:
            print("✅ Leaderboards obtenidos")
            
            # Mover leaderboards al directorio de salida
            leaderboards_source = scraper_script.parent / "leaderboards"
            if leaderboards_source.exists():
                output_dir.mkdir(parents=True, exist_ok=True)
                for f in leaderboards_source.glob("*.csv"):
                    shutil.copy(str(f), str(output_dir / f.name))
                for f in leaderboards_source.glob("my_rank_*.txt"):
                    shutil.copy(str(f), str(output_dir / f.name))
                print(f"📄 Leaderboards guardados en: {output_dir}")
                return True
        else:
            print(f"⚠️ Warning al obtener leaderboards: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"[ERROR] Error ejecutando scraper: {e}")
        return False
    
    return False


def build_segments_json_from_csv(segments_csv: Path, output_file: Path) -> bool:
    """
    Convierte segments.csv a segments.json con el formato esperado por segment_matcher.
    """
    import csv
    
    if not segments_csv.exists():
        return False
    
    segments = []
    with open(segments_csv, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            seg_id = row.get('segment_id', '').strip()
            seg_name = row.get('segment_name', '').strip()
            if seg_id:
                # Datos básicos - las coordenadas se obtendrán del scraping o GPX
                segments.append({
                    'id': seg_id,
                    'name': seg_name,
                    'start_lat': 0,  # Se completará desde el GPX
                    'start_lon': 0,
                    'end_lat': 0,
                    'end_lon': 0,
                    'distance': 0
                })
    
    data = {'segments': segments}
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    return True


def enrich_segments_with_strava_api(segments_json: Path, activity_url: str) -> bool:
    """
    Usa la API de Strava para obtener coordenadas exactas de cada segmento.
    """
    try:
        # Intentar usar datos de la API si tenemos token
        STRAVA_PROJECT = PROJECT_ROOT.parent / "Strava-Scraper-Leaderboard"
        sys.path.insert(0, str(STRAVA_PROJECT))
        from auth_strava import load_env
        
        env_path = STRAVA_PROJECT / ".env"
        if not env_path.exists():
            return False
        
        env = load_env(env_path)
        token = env.get('STRAVA_ACCESS_TOKEN')
        
        if not token:
            return False
        
        import requests
        
        with open(segments_json, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        headers = {"Authorization": f"Bearer {token}"}
        
        for seg in data['segments']:
            seg_id = seg['id']
            try:
                resp = requests.get(
                    f"https://www.strava.com/api/v3/segments/{seg_id}",
                    headers=headers,
                    timeout=15
                )
                if resp.status_code == 200:
                    api_data = resp.json()
                    # Extraer coordenadas de inicio y fin
                    # La API devuelve arrays [lat, lon]
                    start_latlng = api_data.get('start_latlng')
                    end_latlng = api_data.get('end_latlng')
                    if start_latlng and len(start_latlng) >= 2:
                        seg['start_lat'] = start_latlng[0]
                        seg['start_lon'] = start_latlng[1]
                    if end_latlng and len(end_latlng) >= 2:
                        seg['end_lat'] = end_latlng[0]
                        seg['end_lon'] = end_latlng[1]
                    seg['distance'] = api_data.get('distance', 0)
            except Exception as e:
                print(f"  ⚠️ No se pudieron obtener datos del segmento {seg_id}: {e}")
        
        with open(segments_json, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        return True
        
    except Exception as e:
        print(f"  ⚠️ Error enriqueciendo segmentos: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Prepara datos de segmentos Strava para overlay en videos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  # Modo automático (recomendado):
  %(prog)s --gpx MiCarrera.gpx --activity-url https://www.strava.com/activities/12345678

  # Modo manual (si ya tenés los datos):
  %(prog)s --gpx MiCarrera.gpx --segments-file segments.json --leaderboards-dir leaderboards/
        """
    )
    
    # Inputs
    parser.add_argument("--gpx", type=Path, required=True,
                        help="Archivo GPX del recorrido")
    
    # Modo automático
    parser.add_argument("--activity-url", type=str,
                        help="URL de la actividad Strava (ej: https://www.strava.com/activities/12345678)")
    
    # Modo manual
    parser.add_argument("--segments-file", type=Path,
                        help="JSON con datos de segmentos (modo manual)")
    parser.add_argument("--leaderboards-dir", type=Path,
                        help="Directorio con CSVs de leaderboards (modo manual)")
    
    # Output
    parser.add_argument("--output", type=Path, default=Path("segments_timed.json"),
                        help="Archivo JSON de salida (default: segments_timed.json)")
    
    # Configuración
    parser.add_argument("--preview-distance", type=float, default=100.0,
                        help="Distancia de anticipación para mostrar overlay (metros, default: 100)")
    parser.add_argument("--work-dir", type=Path, default=Path(".segment_work"),
                        help="Directorio temporal de trabajo")
    
    args = parser.parse_args()
    
    # Validar argumentos
    if not args.activity_url and not args.segments_file:
        parser.error("Debes especificar --activity-url o --segments-file")
    
    if not args.gpx.exists():
        print(f"[ERROR] No se encontró el archivo GPX: {args.gpx}")
        sys.exit(1)
    
    # Crear directorio de trabajo
    work_dir = args.work_dir
    work_dir.mkdir(parents=True, exist_ok=True)
    
    print("=" * 60)
    print("🏁 PREPARANDO DATOS DE SEGMENTOS STRAVA")
    print("=" * 60)
    
    # Paso 1: Obtener segmentos
    segments_json = work_dir / "segments.json"
    
    if args.activity_url:
        print("\n📥 PASO 1: Obteniendo segmentos de Strava API...")
        csv_file = work_dir / "segments_from_api.csv"
        if run_segments_retriever(args.activity_url, work_dir / "segments_api"):
            # Convertir CSV a JSON
            if csv_file.exists():
                build_segments_json_from_csv(csv_file, segments_json)
                # Intentar enriquecer con API
                enrich_segments_with_strava_api(segments_json, args.activity_url)
        else:
            print("[ERROR] No se pudieron obtener segmentos de la API")
            sys.exit(1)
    elif args.segments_file:
        print(f"\n📄 Usando segmentos proporcionados: {args.segments_file}")
        import shutil
        shutil.copy(str(args.segments_file), str(segments_json))
    
    if not segments_json.exists():
        print("[ERROR] No hay archivo de segmentos disponible")
        sys.exit(1)
    
    # Verificar/estimar coordenadas de segmentos desde GPX si faltan
    print("\n📍 Verificando coordenadas de segmentos...")
    with open(segments_json, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    needs_matching = any(
        seg.get('start_lat', 0) == 0 and seg.get('start_lon', 0) == 0
        for seg in data.get('segments', [])
    )
    
    if needs_matching:
        print("  ⚠️ Algunos segmentos no tienen coordenadas")
        print("  El matcher intentará ubicarlos por cercanía en el GPX")
    
    # Paso 2: Obtener leaderboards
    leaderboards_dir = work_dir / "leaderboards"
    
    if args.activity_url:
        print("\n🏆 PASO 2: Obteniendo leaderboards...")
        csv_file = work_dir / "segments_from_api.csv"
        if not csv_file.exists():
            csv_file = work_dir / "segments.csv"
        run_segments_scraper(csv_file, leaderboards_dir)
    elif args.leaderboards_dir:
        print(f"\n📄 Usando leaderboards proporcionados: {args.leaderboards_dir}")
        import shutil
        if args.leaderboards_dir.exists():
            leaderboards_dir.mkdir(parents=True, exist_ok=True)
            for f in args.leaderboards_dir.glob("*.csv"):
                shutil.copy(str(f), str(leaderboards_dir / f.name))
            for f in args.leaderboards_dir.glob("my_rank_*.txt"):
                shutil.copy(str(f), str(leaderboards_dir / f.name))
    
    # Paso 3: Matching con GPX
    print("\n🔗 PASO 3: Vinculando segmentos con GPX...")
    print(f"   GPX: {args.gpx}")
    print(f"   Preview distance: {args.preview_distance}m")
    
    try:
        timed_segments = build_segment_data(
            gpx_file=args.gpx,
            segments_json=segments_json,
            leaderboards_dir=leaderboards_dir,
            output_file=args.output,
            preview_distance_m=args.preview_distance
        )
        
        print(f"\n✅ ÉXITO - {len(timed_segments)} segmentos procesados")
        print(f"📄 Output: {args.output.absolute()}")
        
        # Mostrar resumen
        print("\n📊 RESUMEN:")
        for seg in timed_segments:
            start = seg.start_time.strftime("%H:%M:%S")
            end = seg.end_time.strftime("%H:%M:%S")
            preview = seg.preview_time.strftime("%H:%M:%S")
            pos = seg.my_position or "?"
            print(f"  • {seg.name[:40]:<40} | Preview: {preview} | Inicio: {start} | Pos: #{pos}")
        
        print("\n" + "=" * 60)
        print("🎬 LISTO PARA RENDERIZAR")
        print("=" * 60)
        print(f"\nEjecuta:")
        print(f"  gopro-dashboard.py --gpx {args.gpx} \\")
        print(f"    --segment-data {args.output} \\")
        print(f"    --layout xml --layout-xml segment-layout.xml \\")
        print(f"    input.mp4 output.mp4")
        
    except Exception as e:
        print(f"\n[ERROR] Error en el matching: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
