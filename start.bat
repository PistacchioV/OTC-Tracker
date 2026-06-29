@echo off
REM ============================================================================
REM  OTC Tracker - inicializacao no Windows (maquina JP)
REM
REM  Uso:
REM     start.bat          -> DEBUG  (dev server, auto-reload, porta 8050)
REM     start.bat prod     -> PRODUCAO (waitress, porta 5005)
REM
REM  Acesso:  http://localhost:<porta>   (ou http://<IP-da-maquina>:<porta>)
REM ============================================================================

cd /d "%~dp0"

REM ---------------------------------------------------------------------------
REM  Localiza o python do virtualenv (nao depende do PATH do sistema).
REM  Ajuste o nome da pasta do venv se necessario.
REM ---------------------------------------------------------------------------
set "PY="
if exist "OTCTracker\Scripts\python.exe" set "PY=OTCTracker\Scripts\python.exe"
if not defined PY if exist ".venv311\Scripts\python.exe" set "PY=.venv311\Scripts\python.exe"
if not defined PY if exist ".venv\Scripts\python.exe"    set "PY=.venv\Scripts\python.exe"

REM  Fallback: python global do PATH (ou launcher py).
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

if /I "%~1"=="prod"       goto prod
if /I "%~1"=="production" goto prod

:debug
set DEBUG=True
echo.
echo [DEBUG] OTC Tracker em http://0.0.0.0:8050  (Werkzeug dev server, auto-reload)
echo.
"%PY%" run.py
goto end

:prod
set DEBUG=False
echo.
echo [PRODUCAO] OTC Tracker em http://0.0.0.0:5005  (waitress)
echo.
REM gunicorn nao roda no Windows; usamos waitress como servidor WSGI de producao.
"%PY%" -m waitress --host=0.0.0.0 --port=5005 run:app
if errorlevel 1 (
    echo.
    echo [ERRO] waitress nao encontrado. Instale com:  "%PY%" -m pip install waitress
)
goto end

:end
pause
