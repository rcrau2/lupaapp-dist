@echo off
setlocal

echo.
echo ============================================================
echo   LupaApp -- Build Script
echo ============================================================
echo.

echo [1/4] Instalando dependencias Python...
pip install -r requirements.txt
if errorlevel 1 ( echo ERROR: pip install fallo. & pause & exit /b 1 )

echo.
echo [2/4] Instalando PyInstaller...
pip install pyinstaller
if errorlevel 1 ( echo ERROR: no se pudo instalar PyInstaller. & pause & exit /b 1 )

echo.
echo [3/4] Compilando ejecutable...
pyinstaller ^
    --onefile ^
    --windowed ^
    --name "LupaApp" ^
    --hidden-import=pystray._win32 ^
    --hidden-import=pynput.keyboard._win32 ^
    --hidden-import=pynput.mouse._win32 ^
    --hidden-import=mss.windows ^
    --hidden-import=PIL._tkinter_finder ^
    --collect-submodules=mss ^
    --collect-submodules=pynput ^
    --collect-submodules=pystray ^
    app\main.py

if errorlevel 1 ( echo ERROR: PyInstaller fallo. & pause & exit /b 1 )

echo.
echo [4/4] Copiando ejecutable a web\dist\ ...
if not exist web\dist mkdir web\dist
copy /Y dist\LupaApp.exe web\dist\LupaApp.exe
if errorlevel 1 ( echo AVISO: no se pudo copiar a web\dist\. Copia manualmente dist\LupaApp.exe )

echo.
echo ============================================================
echo   BUILD COMPLETADO
echo   Ejecutable local : dist\LupaApp.exe
echo   Para el servidor : web\dist\LupaApp.exe
echo.
echo   Proximos pasos:
echo     1. Sube el proyecto a tu VPS con git o SCP.
echo     2. En el VPS ejecuta:  docker compose up -d --build
echo     3. La pagina de descarga quedara en http://TU_IP/
echo ============================================================
echo.
pause
