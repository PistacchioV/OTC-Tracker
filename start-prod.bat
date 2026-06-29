@echo off
REM ============================================================================
REM  OTC Tracker - PRODUCAO (Windows, maquina JP)
REM
REM  Waitress (servidor WSGI), porta 8050.
REM  Acesso:  http://localhost:8050   (ou http://<IP-da-maquina>:8050)
REM
REM  Uso:
REM     start-prod.bat             -> tenta instalar requirements e sobe
REM     start-prod.bat noinstall   -> pula a instalacao (util offline)
REM ============================================================================

cd /d "%~dp0"

REM ---------------------------------------------------------------------------
REM  Localiza o python do virtualenv (nao depende do PATH do sistema).
REM  Tudo ancorado em %~dp0 (pasta deste .bat, ja termina com \), entao
REM  funciona mesmo que o diretorio atual seja outro. O venv pode estar na
REM  raiz do projeto (Scripts\) ou numa subpasta.
REM ---------------------------------------------------------------------------
set "BASE=%~dp0"
set "PY="
if exist "%BASE%Scripts\python.exe"            set "PY=%BASE%Scripts\python.exe"
if not defined PY if exist "%BASE%OTCTracker\Scripts\python.exe" set "PY=%BASE%OTCTracker\Scripts\python.exe"
if not defined PY if exist "%BASE%.venv311\Scripts\python.exe"   set "PY=%BASE%.venv311\Scripts\python.exe"
if not defined PY if exist "%BASE%.venv\Scripts\python.exe"      set "PY=%BASE%.venv\Scripts\python.exe"

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
REM  Instala as dependencias (best-effort). Se a rede bloquear o pypi, avisa
REM  e continua - as deps normalmente ja estao instaladas no venv.
REM  Para pular: start-prod.bat noinstall
REM ---------------------------------------------------------------------------
if /I "%~1"=="noinstall" (
    echo [INFO] Instalacao de dependencias pulada (noinstall).
) else (
    echo.
    echo [INFO] Instalando dependencias (requirements.txt)...
    "%PY%" -m pip install -r "%BASE%requirements.txt" --timeout 10 --retries 1 --disable-pip-version-check
    if errorlevel 1 (
        echo.
        echo [AVISO] Nao foi possivel instalar/atualizar as dependencias ^(rede/pypi^).
        echo         Seguindo com o que ja esta instalado no venv...
        echo.
    )
)

set FLASK_APP=run.py
set DEBUG=False
echo.
echo [PRODUCAO] OTC Tracker em http://0.0.0.0:8050  (waitress)
echo.
REM gunicorn nao roda no Windows; usamos waitress como servidor WSGI de producao.
"%PY%" -m waitress --host=0.0.0.0 --port=8050 run:app
if errorlevel 1 (
    echo.
    echo [ERRO] waitress nao encontrado. Instale com:  "%PY%" -m pip install waitress
)

pause
