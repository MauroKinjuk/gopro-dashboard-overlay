@echo off
REM Script para preview de layout 4K (3840x2160)
REM Uso: layout-4k.bat

REM Detectar directorio del proyecto (directorio padre de donde está este script)
for %%I in ("%~dp0..") do set "PROJECT_DIR=%%~fI"

echo Abriendo layout editor 4K...

python "%PROJECT_DIR%\bin\gopro-layout.py" ^
  "%PROJECT_DIR%\gopro_overlay\layouts\Bici_4k_3840x2160.xml" ^
  --font "%PROJECT_DIR%\Coolvetica.otf" ^
  --overlay-size 3840x2160
