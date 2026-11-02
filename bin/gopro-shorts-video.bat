@echo off
REM Script para generar overlay Shorts (1080x1920) solo para la parte del GPX
REM que coincide con las fechas de un video
REM Uso: gopro-shorts-video.bat <ruta_al_gpx> <ruta_al_video> [nombre_salida]

REM Detectar directorio del proyecto (directorio padre de donde está este script)
for %%I in ("%~dp0..") do set "PROJECT_DIR=%%~fI"

if "%~1"=="" (
    echo Error: Debes especificar la ruta al archivo GPX
    echo Uso: gopro-shorts-video.bat "ruta\a\tu_archivo.gpx" "ruta\a\tu_video.mp4" [nombre_salida]
    exit /b 1
)

if "%~2"=="" (
    echo Error: Debes especificar la ruta al video
    echo Uso: gopro-shorts-video.bat "ruta\a\tu_archivo.gpx" "ruta\a\tu_video.mp4" [nombre_salida]
    exit /b 1
)

set "GPX_FILE=%~1"
set "VIDEO_FILE=%~2"

if "%~3"=="" (
    for %%F in ("%VIDEO_FILE%") do set "OUTPUT_NAME=%%~nF-shorts.mov"
) else (
    set "OUTPUT_NAME=%~3"
)

REM 4o argumento opcional: fecha de inicio UTC "YYYY-MM-DD HH:MM:SS"
REM para corregir manualmente la sincronizacion
if not "%~4"=="" (
    set "ALIGN_ARG=--start-date "%~4""
) else (
    set "ALIGN_ARG=--video-time-start video-created"
)

echo Generando overlay Shorts para video: %VIDEO_FILE%
echo Usando GPX: %GPX_FILE%
echo Salida: %OUTPUT_NAME%

python "%PROJECT_DIR%\bin\gopro-dashboard.py" ^
  "%VIDEO_FILE%" ^
  "%OUTPUT_NAME%" ^
  --font "%PROJECT_DIR%\Coolvetica.otf" ^
  --use-gpx-only ^
  --gpx "%GPX_FILE%" ^
  %ALIGN_ARG% ^
  --generate overlay ^
  --profile overlay-capcut ^
  --overlay-size 1080x1920 ^
  --units-speed kph ^
  --exclude temperature,moving_map ^
  --layout-xml "%PROJECT_DIR%\gopro_overlay\layouts\Bici_Shorts_1080x1920.xml"
