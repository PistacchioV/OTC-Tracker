@echo off
setlocal

rem ===========================================================================
rem  OTC Tracker - subida da instancia do time (o .bat que mora no SHARE).
rem
rem  Esta versao corrige quatro coisas da anterior (21/09/2026):
rem
rem   1. PYTHONPYCACHEPREFIX (HANDOFF 322) -- NAO existia.  Sem ele o Python
rem      compila os ~600 modulos do app e grava cada .pyc DE VOLTA no share,
rem      com escrita atomica (arquivo temporario + rename), um por modulo e
rem      sem imprimir nada.  Acontece toda vez que o %VERSION_PATH% muda, que
rem      e quando a pasta nova ainda nao tem __pycache__ nenhum.
rem   2. `ds tool install python3.12` estava GRUDADO com um `cd ... && flask
rem      run` de outra colagem.  So dispara em maquina sem o Python 3.12 -- e
rem      nela o install falhava pelo nome de tool inexistente, o `if
rem      errorlevel 1` seguinte disparava e o script saia.  Maquina nova nunca
rem      subia.
rem   3. waitress com threads=8; o desenho do app pede 16 (CLAUDE.md 2).  Com
rem      os dados no share a thread passa a maior parte do request PARADA
rem      esperando rede, e 8 contra os 8 leitores por banco
rem      (DATABASE_READ_CONCURRENCY) param o servidor inteiro.
rem   4. `ds tool list` rodava DUAS vezes -- duas idas a rede antes de
rem      qualquer coisa aparecer na tela.  Agora e uma, com a saida em cache
rem      e com `call` (ver o comentario la embaixo: sem ele o .bat entrega o
rem      controle ao `ds` e NUNCA VOLTA -- o pipe da versao antiga escondia
rem      isso, porque cada lado de um pipe roda num processo proprio).
rem
rem  E acrescenta marcadores [TIME]: eles respondem quanto da subida e este
rem  .bat e quanto e o app.  O app so comeca a imprimir depois do ultimo
rem  marcador; ate 21/09/2026 o trecho de dentro dele levava ~15 min (sao 177
rem  aberturas de DuckDB no share, todas da semeadura de dados da subida).
rem ===========================================================================

echo [TIME] inicio do .bat            %TIME%

set "PYTHON_COMMAND=python"
set "SHARE_ROOT=\\NAWEST.ad.jpmorganchase.com\LAC\BRA\intra\Confirmation\Derivativos\OTC Tracker\Application"

rem Skip pip's self-update check and interactive prompts - one less network
rem round-trip on every install call below.
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "PIP_NO_INPUT=1"

rem UMA chamada ao `ds tool list` para as duas perguntas abaixo: cada uma era
rem uma ida a rede, e a resposta e a mesma nas duas.
rem
rem O `call` NAO e enfeite: o `ds` e um script do shell (.cmd/.bat), e um .bat
rem que chama outro SEM `call` entrega o controle de vez -- o segundo roda, o
rem PRIMEIRO NUNCA VOLTA.  Na versao de antes isso nao aparecia porque o
rem `ds tool list | findstr ...` era um PIPE, e o `cmd` roda cada lado de um
rem pipe num processo proprio; trocar o pipe por redirecionamento para arquivo
rem tirou essa protecao acidental e a subida morria aqui, calada, logo depois
rem do primeiro [TIME] (21/09/2026).  Vale para todo `ds` deste arquivo.
set "DS_TOOLS=%TEMP%\otc-ds-tools.txt"
call ds tool list > "%DS_TOOLS%" 2>&1

rem O `)` no fim do padrao e literal (o findstr /r nao tem agrupamento) e casa
rem o mesmo `python3.12 (3.12.x)` de antes -- esta ali para o parentese FECHAR:
rem o `check_bat_blocks.py` conta parenteses sem olhar aspas, e um `(` sozinho
rem faz o resto do arquivo parecer estar dentro de um bloco.
findstr /r /c:"python3\.12 (3\.12\..*)" "%DS_TOOLS%" >nul
if errorlevel 1 (
    echo Python 3.12 was not found. Installing it...
    call ds tool install python3.12
    if errorlevel 1 (
        echo Error: Could not install Python 3.12.
        exit /b 1
    )
)

findstr /c:"localproxy-cfg" "%DS_TOOLS%" >nul
if errorlevel 1 (
    echo localproxy-cfg was not found. Installing it...
    call ds tool install localproxy-cfg
    if errorlevel 1 (
        echo Error: Could not install localproxy-cfg.
        exit /b 1
    )
)

echo [TIME] ds tool list conferido    %TIME%

set /p "VERSION_PATH=" < "%SHARE_ROOT%\link.txt"
pushd "%SHARE_ROOT%\otc-source\%VERSION_PATH%" || exit /b 1
set "REQUIREMENTS_FILE=%SHARE_ROOT%\otc-source\%VERSION_PATH%\requirements.txt"

echo [TIME] share mapeado ^(pushd^)    %TIME%

rem Secret key persisted locally (never on the shared drive) so sessions
rem survive restarts without a hardcoded, guessable value sitting in a
rem script that everyone on the share can read.
set "APP_STATE_DIR=%LOCALAPPDATA%\OTC-Tracker"
if not exist "%APP_STATE_DIR%" mkdir "%APP_STATE_DIR%"
set "SECRET_KEY_FILE=%APP_STATE_DIR%\secret_key.txt"
if not exist "%SECRET_KEY_FILE%" (
    %PYTHON_COMMAND% -c "import secrets; print(secrets.token_hex(32))" > "%SECRET_KEY_FILE%"
)
set /p "SECRET_KEY=" < "%SECRET_KEY_FILE%"

rem Skip both installs below when requirements.txt hasn't changed since the
rem last successful run. Pass --reinstall to force them (e.g. after the JPMC
rem package publishes an update).
set "REQUIREMENTS_SNAPSHOT=%APP_STATE_DIR%\requirements-%VERSION_PATH%.snapshot"
set "SKIP_INSTALL=0"
if /i not "%~1"=="--reinstall" if exist "%REQUIREMENTS_SNAPSHOT%" (
    fc /b "%REQUIREMENTS_FILE%" "%REQUIREMENTS_SNAPSHOT%" >nul 2>&1
    if not errorlevel 1 set "SKIP_INSTALL=1"
)

if "%SKIP_INSTALL%"=="1" (
    echo Dependencies already up to date - skipping install ^(use --reinstall to force^).
) else (
    if exist "%REQUIREMENTS_FILE%" (
        echo Installing Python dependencies...
        %PYTHON_COMMAND% -m pip install --prefer-binary -r "%REQUIREMENTS_FILE%"
        if errorlevel 1 (
            echo Error: Could not install Python dependencies.
            popd
            exit /b 1
        )
    )

    echo Installing JPMC Python package...
    %PYTHON_COMMAND% -m pip install --prefer-binary --index-url https://artifacts.jpmchase.net/artifactory/api/pypi/pypi/simple/ "awmpythoninnovation-awmpy[kerberos]"
    if errorlevel 1 (
        echo Error: Could not install the JPMC Python package.
        popd
        exit /b 1
    )

    copy /y "%REQUIREMENTS_FILE%" "%REQUIREMENTS_SNAPSHOT%" >nul
)

echo [TIME] dependencias conferidas   %TIME%

rem ---------------------------------------------------------------------------
rem  Bytecode (.pyc) em disco LOCAL, nunca no share (HANDOFF 322).
rem
rem  O Python espelha a arvore do fonte dentro do prefixo DESCARTANDO a letra
rem  da unidade, entao o `pushd` acima pode mapear o share em qualquer letra
rem  livre que o cache continua o mesmo.  Mas a raiz mapeada JA E a pasta da
rem  versao, entao o caminho espelhado comeca em `apps\...` e duas versoes
rem  cairiam no mesmo lugar -- dai o %VERSION_PATH% no prefixo.
rem
rem  %LOCALAPPDATA% e nao %TEMP%: e onde este .bat ja guarda o que precisa
rem  sobreviver ao restart (a secret key e o snapshot do requirements), e o
rem  %TEMP% e alvo de Limpeza de Disco e de GPO -- limpo, a subida seguinte
rem  recompila tudo.  E NUNCA PYTHONDONTWRITEBYTECODE: ele evita a escrita
rem  mas recompila a cada subida, e a instancia reinicia varias vezes por dia.
rem ---------------------------------------------------------------------------
set "PYCACHE_DIR=%APP_STATE_DIR%\pycache\%VERSION_PATH%"
if not defined PYTHONPYCACHEPREFIX set "PYTHONPYCACHEPREFIX=%PYCACHE_DIR%"
echo [INFO] Bytecode ^(.pyc^) em: %PYTHONPYCACHEPREFIX%

echo [TIME] entregando ao Python      %TIME%
echo Starting OTC Tracker with Waitress (production WSGI server) on port 8051...

rem threads=16, nao 8 (CLAUDE.md 2: escale com THREADS, nunca com processos --
rem o singleton do banco, o _cache_lock e os schedulers so valem dentro de UM
rem processo).  Com os dados no share a thread fica parada esperando rede na
rem maior parte do request.
%PYTHON_COMMAND% -c "from waitress import serve; from run import app; serve(app, host='0.0.0.0', port=8051, threads=16)"
set "EXIT_CODE=%ERRORLEVEL%"
popd

exit /b %EXIT_CODE%
