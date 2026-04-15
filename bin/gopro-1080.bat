@echo off
REM Script para generar overlay de ciclismo en HD (1920x1080)
REM Uso: gopro-1080.bat <ruta_al_gpx> [nombre_salida]

REM Detectar directorio del proyecto (directorio padre de donde está este script)
for %%I in ("%~dp0..") do set "PROJECT_DIR=%%~fI"

if "%~1"=="" (
    echo Error: Debes especificar la ruta al archivo GPX
    echo Uso: gopro-1080.bat "ruta\a\tu_archivo.gpx" [nombre_salida]
    exit /b 1
)

set "GPX_FILE=%~1"

if "%~2"=="" (
    for %%F in ("%GPX_FILE%") do set "OUTPUT_NAME=%%~nF-dashboard.mov"
) else (
    set "OUTPUT_NAME=%~2"
)

echo Generando overlay 1080p para: %GPX_FILE%
echo Salida: %OUTPUT_NAME%

python "%PROJECT_DIR%\bin\gopro-dashboard.py" ^
  --font "%PROJECT_DIR%\Coolvetica.otf" ^
  --use-gpx-only ^
  --gpx "%GPX_FILE%" ^
  --profile overlay-prores ^
  --overlay-size 1920x1080 ^
  "%OUTPUT_NAME%" ^
  --units-speed kph ^
  --exclude temperature,moving_map ^
  --layout-xml "%PROJECT_DIR%\gopro_overlay\layouts\Bici_HD_1080x1920.xml"
