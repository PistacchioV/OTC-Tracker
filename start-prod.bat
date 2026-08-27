@echo off
REM ============================================================================
REM  OTC Tracker - PRODUCAO (Windows, maquina JP)
REM
REM  Waitress (servidor WSGI), porta 8051.
REM  Acesso:  http://localhost:8051   (ou http://<IP-da-maquina>:8051)
REM
REM  Uso:
REM     start-prod.bat             -> tenta instalar requirements e sobe
REM     start-prod.bat noinstall   -> pula a instalacao (util offline)
REM ============================================================================

REM ---------------------------------------------------------------------------
REM  UNC-safe: este .bat roda de \\NAWEST...\Application, e `cd /d` NAO aceita
REM  caminho UNC -- o cmd responde "UNC paths are not supported", cai em
REM  C:\Windows e segue. Dali, o `run:app` do waitress nao acha o run.py e o
REM  servidor nem sobe. O `pushd` mapeia o share numa letra de unidade
REM  temporaria, e o `popd` a devolve no fim.
REM ---------------------------------------------------------------------------
pushd "%~dp0" 2>nul
if errorlevel 1 (
    echo [ERRO] Nao consegui acessar a pasta: %~dp0
    pause
    exit /b 1
)

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
    popd
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

REM ---------------------------------------------------------------------------
REM  BYTECODE EM DISCO LOCAL. Sem isto o Python grava os .pyc dentro do
REM  __pycache__ de CADA pasta do codigo -- que aqui e o SHARE. Na primeira
REM  subida depois de um pull (quando todo .pyc esta obsoleto) sao centenas de
REM  gravacoes atomicas via rede, uma por modulo: o processo fica minutos
REM  parado em `_write_atomic` do importlib, SEM imprimir nada, e parece
REM  travado. Quem cancela nesse ponto ve um KeyboardInterrupt no meio do
REM  import de uma feature qualquer -- um traceback que aponta para o modulo
REM  que por acaso estava sendo compilado, nao para o problema.
REM
REM  Com o cache numa pasta local o custo cai para leitura do .py pelo share e
REM  gravacao local; a segunda subida em diante nem recompila. Nao use
REM  PYTHONDONTWRITEBYTECODE: ele evita a escrita mas obriga a recompilar
REM  TUDO a cada subida, e a instancia reinicia varias vezes por dia.
REM
REM  %LOCALAPPDATA% e nao %TEMP%: o cache precisa SOBREVIVER aos restarts, e
REM  %TEMP% e alvo de Limpeza de Disco e de GPO -- limpo, a subida seguinte
REM  recompila tudo (nao quebra, so volta a demorar).  O Python espelha a
REM  arvore do fonte dentro do prefixo DESCARTANDO a letra da unidade, entao o
REM  pushd acima pode mapear o share em qualquer letra livre que o cache e o
REM  mesmo -- e por isso tambem que versoes diferentes do codigo precisariam de
REM  prefixos diferentes se rodassem da mesma raiz mapeada.
REM ---------------------------------------------------------------------------
if not defined PYTHONPYCACHEPREFIX set "PYTHONPYCACHEPREFIX=%LOCALAPPDATA%\OTC-Tracker\pycache"
echo [INFO] Bytecode (.pyc) em: %PYTHONPYCACHEPREFIX%

echo.
echo [PRODUCAO] OTC Tracker em http://0.0.0.0:8051  (waitress)
echo.
REM gunicorn nao roda no Windows; usamos waitress como servidor WSGI de producao.
REM
REM  --threads=16 (o padrao do waitress e 4). ESCALE COM THREADS, NUNCA COM
REM  PROCESSOS: o singleton do banco, o _cache_lock e os schedulers so valem
REM  dentro de um processo (CLAUDE.md 4).  Com o banco e os dados no share,
REM  a maior parte do tempo de um request e espera de REDE, e a thread fica
REM  parada segurando a vaga.  Com quatro vagas, quatro esperas dessas param
REM  o servidor inteiro -- inclusive o arquivo estatico e a pagina que o
REM  usuario acabou de pedir, que nem banco usam.
"%PY%" -m waitress --host=0.0.0.0 --port=8051 --threads=16 run:app
if errorlevel 1 (
    echo.
    echo [ERRO] waitress nao encontrado. Instale com:  "%PY%" -m pip install waitress
)

pause
popd
