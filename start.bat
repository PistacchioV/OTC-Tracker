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

REM Ativa o virtualenv se existir (ajuste o nome da pasta se necessario).
if exist "OTCTracker\Scripts\activate.bat" (
    call "OTCTracker\Scripts\activate.bat"
) else if exist ".venv311\Scripts\activate.bat" (
    call ".venv311\Scripts\activate.bat"
) else if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
)

set FLASK_APP=run.py

if /I "%~1"=="prod"       goto prod
if /I "%~1"=="production" goto prod

:debug
set DEBUG=True
echo.
echo [DEBUG] OTC Tracker em http://0.0.0.0:8050  (Werkzeug dev server, auto-reload)
echo.
python run.py
goto end

:prod
set DEBUG=False
echo.
echo [PRODUCAO] OTC Tracker em http://0.0.0.0:5005  (waitress)
echo.
REM gunicorn nao roda no Windows; usamos waitress como servidor WSGI de producao.
waitress-serve --host=0.0.0.0 --port=5005 run:app
if errorlevel 1 (
    echo.
    echo [ERRO] waitress nao encontrado. Instale com:  pip install waitress
)
goto end

:end
pause
