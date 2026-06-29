@echo off
REM ============================================================================
REM  OTC Tracker - DEBUG (Windows, maquina JP)
REM
REM  Werkzeug dev server, auto-reload, porta 8050.
REM  Acesso:  http://localhost:8050   (ou http://<IP-da-maquina>:8050)
REM ============================================================================

cd /d "%~dp0"

REM ---------------------------------------------------------------------------
REM  Localiza o python do virtualenv (nao depende do PATH do sistema).
REM ---------------------------------------------------------------------------
set "PY="
if exist "OTCTracker\Scripts\python.exe" set "PY=OTCTracker\Scripts\python.exe"
if not defined PY if exist ".venv311\Scripts\python.exe" set "PY=.venv311\Scripts\python.exe"
if not defined PY if exist ".venv\Scripts\python.exe"    set "PY=.venv\Scripts\python.exe"

if not defined PY (
    where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
    where py >nul 2>&1 && set "PY=py"
)

if not defined PY (
    echo.
    echo [ERRO] Python nao encontrado. Crie o virtualenv OTCTracker ou instale o Python no PATH.
    echo        Ex.:  python -m venv OTCTracker
    echo.
    pause
    exit /b 1
)

echo [INFO] Usando Python: %PY%

REM ---------------------------------------------------------------------------
REM  Instala/atualiza as dependencias.
REM ---------------------------------------------------------------------------
echo.
echo [INFO] Instalando dependencias (requirements.txt)...
"%PY%" -m pip install --upgrade pip
"%PY%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERRO] Falha ao instalar as dependencias. Veja as mensagens acima.
    echo.
    pause
    exit /b 1
)

set FLASK_APP=run.py
set DEBUG=True
echo.
echo [DEBUG] OTC Tracker em http://0.0.0.0:8050  (Werkzeug dev server, auto-reload)
echo.
"%PY%" run.py

pause
