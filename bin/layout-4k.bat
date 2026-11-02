@echo off
REM Script para preview de layout 4K (3840x2160)
REM Uso: layout-4k.bat [nombre_layout.xml] [archivo.fit|.gpx]
REM      layout-4k.bat "ruta\archivo.fit"            -> layout default + datos reales
REM Si no se indica layout, usa Bici_4k_Propuesta_3840x2160.xml

REM Detectar directorio del proyecto (directorio padre de donde está este script)
for %%I in ("%~dp0..") do set "PROJECT_DIR=%%~fI"

set "LAYOUT_FILE=%PROJECT_DIR%\gopro_overlay\layouts\Bici_4k_Propuesta_3840x2160.xml"
set "DATA_FILE="

REM Si el 1er argumento es .fit/.gpx, es el archivo de datos (no un layout)
if /i "%~x1"==".fit" (
    set "DATA_FILE=%~1"
) else if /i "%~x1"==".gpx" (
    set "DATA_FILE=%~1"
) else if not "%~1"=="" (
    set "LAYOUT_FILE=%PROJECT_DIR%\gopro_overlay\layouts\%~1"
    set "DATA_FILE=%~2"
)

echo Abriendo layout editor 4K: %LAYOUT_FILE%

if "%DATA_FILE%"=="" (
    python "%PROJECT_DIR%\bin\gopro-layout.py" ^
      "%LAYOUT_FILE%" ^
      --font "%PROJECT_DIR%\fonts\BarlowCondensed-ExtraBoldItalic.ttf" ^
      --overlay-size 3840x2160
) else (
    echo Con datos de: %DATA_FILE%
    python "%PROJECT_DIR%\bin\gopro-layout.py" ^
      "%LAYOUT_FILE%" ^
      --font "%PROJECT_DIR%\fonts\BarlowCondensed-ExtraBoldItalic.ttf" ^
      --overlay-size 3840x2160 ^
      --gpx "%DATA_FILE%"
)
