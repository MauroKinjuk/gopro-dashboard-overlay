@echo off
REM Script para generar overlay de segmentos Strava desde GPX (sin video de entrada)
REM Uso: gopro-segments.bat <ruta_al_gpx> <ruta_a_segments_timed.json> [nombre_salida] [modo]
REM
REM Modos:
REM   only     - Solo segmentos, sin otras métricas (default)
REM   full     - Segmentos + velocidad + mapa + etc (como segment-layout.xml)
REM
REM Ejemplos:
REM   gopro-segments.bat "carrera.gpx" "segments_timed.json"
REM   gopro-segments.bat "carrera.gpx" "segments_timed.json" "output.mov" full

REM Detectar directorio del proyecto (directorio padre de donde está este script)
for %%I in ("%~dp0..") do set "PROJECT_DIR=%%~fI"

if "%~1"=="" (
    echo Error: Debes especificar la ruta al archivo GPX
    echo.
    echo Uso: gopro-segments.bat ^<GPX^> ^<SEGMENTOS_JSON^> [salida] [modo]
    echo.
    echo Parametros:
    echo   %%1 - Ruta al archivo GPX
    echo   %%2 - Ruta al archivo JSON con datos de segmentos
    echo   %%3 - Nombre de salida (opcional, default: {nombre_gpx}-segments.mov)
    echo   %%4 - Modo: 'only' o 'full' (default: only)
    echo.
    echo Ejemplo:
    echo   gopro-segments.bat "ruta\a\carrera.gpx" "segments_timed.json"
    exit /b 1
)

if "%~2"=="" (
    echo Error: Debes especificar la ruta al archivo JSON de segmentos
    echo Uso: gopro-segments.bat "ruta.gpx" "segments_timed.json"
    exit /b 1
)

set "GPX_FILE=%~1"
set "SEGMENTS_FILE=%~2"

if "%~3"=="" (
    for %%F in ("%GPX_FILE%") do set "OUTPUT_NAME=%%~nF-segments.mov"
) else (
    set "OUTPUT_NAME=%~3"
)

REM Modo de layout
set "MODE=%~4"
if "%~4"=="" set "MODE=only"

if /I "%MODE%"=="full" (
    set "LAYOUT_FILE=%PROJECT_DIR%\gopro_overlay\layouts\segment-layout.xml"
    echo Modo: FULL (segmentos + velocidad + mapa)
) else (
    set "LAYOUT_FILE=%PROJECT_DIR%\gopro_overlay\layouts\segment-only-layout.xml"
    echo Modo: ONLY (solo segmentos)
)

echo.
echo ========================================
echo   GENERANDO OVERLAY DE SEGMENTOS
echo ========================================
echo GPX: %GPX_FILE%
echo Segmentos: %SEGMENTS_FILE%
echo Salida: %OUTPUT_NAME%
echo Layout: %LAYOUT_FILE%
echo ========================================
echo.

REM Copiar el archivo de segmentos al directorio esperado por el layout
if exist "%SEGMENTS_FILE%" (
    copy /Y "%SEGMENTS_FILE%" "%PROJECT_DIR%\segments_timed.json" >nul
    echo [OK] Archivo de segmentos copiado
) else (
    echo [ERROR] No se encontró: %SEGMENTS_FILE%
    exit /b 1
)

echo [OK] Generando overlay con FONDO TRANSPARENTE... (esto puede tomar varios minutos)
echo   Codec: QuickTime Animation (Alpha)
echo.

python "%PROJECT_DIR%\bin\gopro-dashboard.py" ^
  --font "%PROJECT_DIR%\Coolvetica.otf" ^
  --use-gpx-only ^
  --gpx "%GPX_FILE%" ^
  --profile alpha-qtrle ^
  --overlay-size 1920x1080 ^
  "%OUTPUT_NAME%" ^
  --units-speed kph ^
  --layout xml ^
  --layout-xml "%LAYOUT_FILE%" ^
  --include segment_overlay

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Falló la generación del overlay
    exit /b 1
)

echo.
echo ========================================
echo ✅ OVERLAY GENERADO - FONDO TRANSPARENTE
echo ========================================
echo Archivo: %OUTPUT_NAME%
echo Formato: QuickTime MOV con Alpha (transparencia)
echo.
echo Para combinar con tu video en CapCut:
echo 1. Importa el video original y este overlay
echo 2. Coloca el overlay como capa SUPERIOR
echo 3. El fondo transparente se fusiona automaticamente
echo    (No necesitas cambiar blend mode!)
echo.
echo Si el fondo aparece negro en lugar de transparente:
echo - Asegurate de que el archivo sea .mov (no .mp4)
echo - Verifica que uses --profile alpha-qtrle
echo ========================================
