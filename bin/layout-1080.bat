@echo off
REM Script para preview de layout HD (1920x1080)
REM Uso: layout-1080.bat

REM Detectar directorio del proyecto (directorio padre de donde está este script)
for %%I in ("%~dp0..") do set "PROJECT_DIR=%%~fI"

echo Abriendo layout editor 1080p...

python "%PROJECT_DIR%\bin\gopro-layout.py" ^
  "%PROJECT_DIR%\gopro_overlay\layouts\Bici_HD_1080x1920.xml" ^
  --font "%PROJECT_DIR%\Coolvetica.otf" ^
  --overlay-size 1920x1080
