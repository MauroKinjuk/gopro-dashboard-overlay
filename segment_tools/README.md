# Overlay de Segmentos Strava

Esta funcionalidad permite mostrar información de segmentos de Strava directamente sobre tus videos de ciclismo, incluyendo:
- Nombre del segmento
- Leaderboard Top 10
- Tu posición destacada
- Animaciones de entrada (100m antes) y salida

## Componentes

1. **`segment_matcher.py`** - Vincula segmentos de Strava con timestamps de tu GPX
2. **`segment_overlay.py`** - Widget que renderiza la información en el video
3. **`build_segment_overlay_data.py`** - Script orquestador que coordina todo el proceso
4. **`segment-layout.xml`** - Layout de ejemplo con el widget integrado

## Requisitos Previos

### 1. Proyecto Strava-Scraper-Leaderboard

Necesitás el proyecto **Strava-Scraper-Leaderboard** en el mismo directorio que este proyecto (como proyecto "hermano"), o configurar la variable de entorno `STRAVA_PROJECT_PATH`:

```bash
# Opción 1: Proyecto en directorio hermano (default)
#   github/
#   ├── fork-gopro-dashboard-overlay/
#   └── Strava-Scraper-Leaderboard/

# Opción 2: Variable de entorno
export STRAVA_PROJECT_PATH="/ruta/a/Strava-Scraper-Leaderboard"
```

### 2. Configurar Autenticación de Strava

El sistema usa **dos métodos** de autenticación:

#### A. API Token (automático)
Usado por `segments_retriever.py` para obtener lista de segmentos.

**Setup (una sola vez):**
```bash
cd /ruta/a/Strava-Scraper-Leaderboard
python auth_strava.py
```

Esto abrirá el navegador para autorizar la app. Después se guarda automáticamente en `.env`:
```
STRAVA_CLIENT_ID=tu_client_id
STRAVA_CLIENT_SECRET=tu_client_secret
STRAVA_ACCESS_TOKEN=xxx
STRAVA_REFRESH_TOKEN=xxx
```

#### B. Cookies del Navegador (manual)
El scraping de leaderboards **requiere cookies** de una sesión web activa de Strava (limitación de la API pública).

**Cómo obtener las cookies:**

1. Abrí Strava.com en Chrome/Edge y logueate
2. Abri DevTools (F12) → pestaña **Network**
3. Recargá la página (F5)
4. Click en cualquier request a `strava.com` → Headers → **Request Headers**
5. Buscá el campo `cookie:` y copiá TODO el contenido
6. Pegalo en tu `.env`:

```bash
# En Strava-Scraper-Leaderboard/.env agregá:
STRAVA_COOKIES_HEADER="_strava4_session=xxx; _strava4_session_csrf_token=yyy; ..."
```

> ⚠️ **Las cookies expiran** (generalmente en ~6 horas). Si el scraper falla, actualizá las cookies repitiendo el proceso.

### 3. Archivos de Entrada
- **GPX**: Exportado de tu ciclocomputador o Strava
- **URL de actividad**: La URL de tu carrera en Strava (ej: `https://www.strava.com/activities/12345678`)

## Flujo de Trabajo

### Paso 1: Preparar datos de segmentos

```bash
python build_segment_overlay_data.py \
    --gpx "TuArchivo.gpx" \
    --activity-url "https://www.strava.com/activities/XXXXX"
```

Este script:
1. Obtiene los segmentos de tu actividad Strava via API
2. Hace scraping de los leaderboards (top 10)
3. Encuentra en qué momento del GPX corresponde cada segmento
4. Genera `segments_timed.json` con toda la información sincronizada

### Paso 2: Renderizar video con overlay

**Opción A: Con video de entrada**

```bash
venv/bin/gopro-dashboard.py --gpx MiCarrera.gpx --layout xml --layout-xml gopro_overlay/layouts/segment-layout.xml video_input.mp4 video_output.mp4
```

**Opción B: Solo desde GPX (sin video)** ⭐ *Nuevo*

Genera un overlay con **fondo transparente** (canal alpha) que podés componer directamente en CapCut:

```bash
# Solo segmentos (limpio, sin otras métricas)
.\bin\gopro-segments.bat "ruta\a\MiCarrera.gpx" "segments_timed.json"

# Segmentos + velocidad + mapa (completo)
.\bin\gopro-segments.bat "ruta\a\MiCarrera.gpx" "segments_timed.json" "output.mov" full
```

O usando el script Python (más flexible):

```bash
python bin/gopro-segments.py --gpx MiCarrera.gpx --segments segments_timed.json --output overlay.mov --resolution 1080
```

El resultado es un video `.mov` con **fondo transparente** (codec QuickTime Animation con alpha). En CapCut simplemente:
1. Importá el overlay y tu video original
2. Colocá el overlay en una capa superior
3. La transparencia se aplica automáticamente (no necesitás blend mode!)

> **Nota:** El archivo debe ser `.mov` (QuickTime) para preservar el canal alpha. MP4 no soporta transparencia.

## Personalización del Layout XML

Puedes crear tu propio layout XML incluyendo el widget de segmentos:

```xml
<component 
  type="segment_overlay" 
  x="1400" 
  y="50" 
  file="segments_timed.json"
  width="350"
/>
```

Atributos:
- `x`, `y`: Posición en pantalla (esquina superior izquierda del widget)
- `file`: Ruta al archivo JSON con datos de segmentos
- `width`: Ancho del panel (default: 350)

## Sincronización Temporal (GPX-Only)

Cuando generás el overlay desde GPX sin video, la sincronización se basa en los **timestamps del GPX**.

### Cómo funciona

El widget compara la hora actual del frame (`entry.dt`) contra:
- `preview_time`: 100m antes del segmento (aparece el overlay)
- `start_time`: Inicio real del segmento (comienza a mostrar leaderboard)
- `end_time`: Fin del segmento (muestra resumen y desaparece)

### Sincronizar con tu video real

Si el GPX tiene la hora correcta (ej: GPS de tu ciclocomputador), el overlay se sincronizará automáticamente con el momento exacto de tu recorrido.

Si hay diferencia horaria entre el GPX y el video:

1. **Opción simple**: Ajustá el tiempo de inicio del GPX con `--start-time`:
   ```bash
   python bin/gopro-segments.py --gpx carrera.gpx --segments segments_timed.json --start-time 08:30:00
   ```

2. **Opción precisa**: Editá el GPX con GPSBabel o similar para ajustar la hora:
   ```bash
   # Shift tiempo en GPX (ej: sumar 2 horas)
   gpsbabel -i gpx -f input.gpx -x track,move=+2h -o gpx -F output.gpx
   ```

3. **En CapCut**: Ajustá manualmente la posición temporal del overlay para que coincida con el video.

### Layouts disponibles

| Layout | Descripción | Uso |
|--------|-------------|-----|
| `segment-only-layout.xml` | Solo segmentos, fondo limpio | Componer en CapCut |
| `segment-layout.xml` | Segmentos + velocidad + mapa + hora | Standalone o composición |

## Estados del Widget

El widget tiene 3 estados visuales:

### 1. Preview (100m antes)
Aparece 100 metros antes de entrar al segmento con:
- Nombre del segmento
- Indicador "Próximo segmento"
- Animación de entrada deslizante

### 2. Active (dentro del segmento)
Muestra el leaderboard completo:
- Nombre del segmento en header naranja
- Tabla con: Posición, Nombre, Velocidad (km/h), Tiempo
- Tu fila resaltada en amarillo
- Si estás fuera del top 10, aparece al final separado

### 3. Completed (al salir)
Resumen de 3 segundos:
- Check de segmento completado
- Tu posición final y tiempo
- Fade out

## Formato del JSON de Segmentos

Si querés generar el JSON manualmente:

```json
{
  "gpx_file": "MiCarrera.gpx",
  "preview_distance_m": 100,
  "segments": [
    {
      "id": "12345678",
      "name": "Subida al Mirador",
      "start_time": "2024-01-15T08:23:45+00:00",
      "end_time": "2024-01-15T08:25:12+00:00",
      "preview_time": "2024-01-15T08:23:35+00:00",
      "start_point": {"lat": -34.6, "lon": -58.4},
      "end_point": {"lat": -34.61, "lon": -58.41},
      "leaderboard": [
        {"rank": "1", "name": "Juan P.", "speed_kmh": "45.2", "time": "1:15"},
        {"rank": "2", "name": "Pedro G.", "speed_kmh": "43.1", "time": "1:18"},
        ...
      ],
      "my_position": 7,
      "my_time": "1:42",
      "my_speed": "38.5"
    }
  ]
}
```

## Solución de Problemas

### "No se encontraron segmentos"
- Verificá que la actividad Strava tenga segmentos
- Revisá que el token de Strava tenga permiso `activity:read_all`

### "Segmentos no aparecen en el video"
- Verificá que los timestamps del GPX coincidan con el video
- El widget usa el timestamp del GPX para sincronizar
- Si hay diferencia horaria, ajustá el GPX o usá `--video-time-start`

### "Leaderboard vacío" o "No se encontraron segmentos"

**Causa más común:** Cookies expiradas o no configuradas.

**Solución:**
```bash
# Ejecutá el helper de configuración
python setup_strava_auth.py
# Elegí opción 2 (Cookies) y seguí las instrucciones
```

### "401 Unauthorized" en API

**Causa:** Token de API expirado.

**Solución:**
```bash
cd /ruta/a/Strava-Scraper-Leaderboard
python auth_strava.py
# Autorizá nuevamente en el navegador
```

### "Mi posición no aparece"

El scraper busca tu nombre exacto "Mauro Kinjuk" en los leaderboards.

**Si no te encuentra:**
1. Verificá que tu nombre en Strava coincida exactamente
2. O manualmente agregá tu posición en el archivo `my_rank_{segment_id}.txt` que genera el scraper

### "ModuleNotFoundError: No module named 'requests'"

**Solución:**
```bash
# En el proyecto Strava-Scraper-Leaderboard
pip install requests beautifulsoup4
```

## Flujo Completo Paso a Paso

### Primera vez (setup inicial)

```bash
# 1. Configurar credenciales (guía interactiva)
python setup_strava_auth.py

# 2. Elegí opción 4 (Todo el proceso completo)
# Seguí las instrucciones en pantalla
```

### Para cada carrera (uso normal)

```bash
# 1. Preparar datos de segmentos
python build_segment_overlay_data.py --gpx "C:\Users\tordy\Downloads\Vuelta_ciclista_por_la_mañana.gpx" --activity-url "https://www.strava.com/activities/16854423062" --output segments_timed.json

# 2. Generar videos de leaderboard (un video por segmento)
python segment_tools/generate_videos.py --segments segments_timed.json --output-dir ./segment_videos

# 2b. Generar solo los primeros N segmentos (ej: solo el primero)
python segment_tools/generate_videos.py --segments segments_timed.json --output-dir ./segment_videos --limit 1

# 3. Los videos estan en segment_videos/ - importalos en CapCut!
```

## Generador de videos por segmento (calidad y formatos)

El script `segment_tools/generate_videos.py` ahora soporta escalado responsive del layout para mantener alineación visual en distintas resoluciones.

### Resoluciones rápidas (presets)

```bash
# 4K horizontal
python segment_tools/generate_videos.py --segments segments_timed.json --output-dir ./segment_videos --preset 4k

# 1080p horizontal
python segment_tools/generate_videos.py --segments segments_timed.json --output-dir ./segment_videos --preset 1080

# Short vertical (9:16)
python segment_tools/generate_videos.py --segments segments_timed.json --output-dir ./segment_videos --preset short
```

### Escala del panel dentro del video

Por defecto el leaderboard ocupa el **70%** del encuadre final (centrado).  
Podés ajustarlo con `--panel-scale` (`0.35` a `1.0`):

```bash
# 4K con panel al 70% (default)
python segment_tools/generate_videos.py --segments segments_timed.json --output-dir ./segment_videos --preset 4k --panel-scale 0.70

# 1080 con panel más grande
python segment_tools/generate_videos.py --segments segments_timed.json --output-dir ./segment_videos --preset 1080 --panel-scale 0.85
```

### Preview estático (sin renderizar video completo)

Para ver cómo quedaría el diseño, podés exportar imágenes PNG:

```bash
# Preview de la fase principal (position)
python segment_tools/generate_videos.py --segments segments_timed.json --output-dir ./segment_videos --preset 4k --panel-scale 0.70 --preview-image --preview-phase position --preview-t 0.82

# Preview de intro
python segment_tools/generate_videos.py --segments segments_timed.json --output-dir ./segment_videos --preset short --preview-image --preview-phase intro --preview-t 0.60
```

Parámetros de preview:
- `--preview-image`: genera `.png` por segmento (en vez de `.mov`)
- `--preview-phase`: `intro | building | position | closing`
- `--preview-t`: instante normalizado dentro de la fase (`0.0` a `1.0`)

## Guía Visual: Obtener Cookies

Si te resulta más fácil con imágenes, seguí estos pasos exactos:

1. **Abrir DevTools**
   - Chrome/Edge: Presioná `F12` o `Ctrl+Shift+I`
   - Se abre una ventana abajo/al costado

2. **Ir a la pestaña Network (Red)**
   - Click en "Network" o "Red"
   - Si no ves nada, recargá la página con `F5`

3. **Encontrar el request**
   - En la lista, buscá algo que diga `strava.com` o `heatmap`
   - Click en ese request

4. **Copiar cookies**
   - Scroll hasta "Request Headers"
   - Buscá `cookie:` 
   - Seleccioná todo el valor (es largo!)
   - Copiá (Ctrl+C)

5. **Pegar en .env**
   - Abrí `Strava-Scraper-Leaderboard/.env`
   - Agregá:
   ```
   STRAVA_COOKIES_HEADER="copiá_acá_todo"
   ```

## Mejoras Futuras

Ideas para extender esta funcionalidad:

1. **Mapa de segmento**: Mini-mapa mostrando solo el tramo del segmento
2. **Gráfico de velocidad**: Curva de velocidad comparada con el KOM
3. **Power-up**: Integrar datos de potencia si tenés medidor
4. **Comparativa en vivo**: Mostrar "+12s vs PR" mientras pedaleás
5. **Segmentos favoritos**: Marcar ciertos segmentos para siempre mostrarlos

