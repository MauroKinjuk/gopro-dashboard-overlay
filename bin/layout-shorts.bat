@echo off
REM Script para preview de layout Shorts (1080x1920)
REM Uso: layout-shorts.bat

REM Detectar directorio del proyecto (directorio padre de donde está este script)
for %%I in ("%~dp0..") do set "PROJECT_DIR=%%~fI"

echo Abriendo layout editor Shorts...

python "%PROJECT_DIR%\bin\gopro-layout.py" ^
  "%PROJECT_DIR%\gopro_overlay\layouts\Bici_Shorts_1080x1920.xml" ^
  --font "%PROJECT_DIR%\Coolvetica.otf" ^
  --overlay-size 1080x1920
