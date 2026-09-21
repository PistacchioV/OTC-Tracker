@echo off
setlocal

rem ===========================================================================
rem  OTC Tracker - SUBIDA DE TESTE: o codigo roda de DISCO LOCAL.
rem
rem  Este arquivo e uma copia do `start-otc-tracker.bat` com UMA diferenca, e
rem  existe para MEDIR se ela vale a pena.  Nao substitua o .bat de producao por
rem  ele antes de ter os numeros -- a mesa sobe pelo outro.
rem
rem  ── O problema ────────────────────────────────────────────────────────────
rem
rem  A subida da instancia leva ~12 min entre `[TIME] entregando ao Python` e o
rem  `Serving on`, e ~8 desses minutos sao um vao MUDO dentro do import do app.
rem  Mudo porque o farol do `database_access` so avisa acima de ~5s por
rem  operacao, e o que acontece ali fica logo abaixo -- centenas de vezes.
rem
rem  Com o codigo no share, CADA um dos ~313 modulos do app paga, no import:
rem
rem    1. a listagem do diretorio do pacote        -> ida e volta no SMB
rem    2. um `stat` no .py, para mtime e tamanho   -> ida e volta no SMB
rem    3. a conferencia do .pyc no PYTHONPYCACHEPREFIX  -> disco local, rapido
rem    4. batendo, carrega o .pyc                  -> disco local, rapido
rem    5. nao batendo, LE o .py inteiro pelo SMB e recompila
rem
rem  O PYTHONPYCACHEPREFIX (que o .bat de producao ja tem) resolve o passo 5 na
rem  maioria das vezes.  Ele NAO dispensa os passos 1 e 2 -- e sao eles que se
rem  repetem em toda subida, tenha havido deploy ou nao.  Em disco local isso e
rem  microssegundo; num share corporativo, cada um custa de milissegundos a mais
rem  de um segundo, e 313 viram minutos.
rem
rem  ── O que este .bat faz de diferente ──────────────────────────────────────
rem
rem  Espelha `otc-source\%VERSION_PATH%` para o disco local com robocopy e faz o
rem  `pushd` NO ESPELHO.  A copia e sequencial em bloco, que e o que o SMB faz
rem  bem, em vez de centenas de aberturas aleatorias, que e o que ele faz mal.
rem  Dali em diante os cinco passos acima acontecem todos em disco local.
rem
rem  ── Por que isso e seguro ─────────────────────────────────────────────────
rem
rem  SO O CODIGO se move.  `DATA_DIR`, `DATABASE_DIR` e `SHARED_DRIVE_ROOT` saem
rem  do `apps/config.py` como caminhos UNC ABSOLUTOS, nao do diretorio atual --
rem  entao trocar o `pushd` nao move um byte de dado.  Os bancos continuam no
rem  share, a mesa inteira continua enxergando os mesmos, e o modelo de "cada
rem  pessoa roda a propria instancia sobre o MESMO db/" fica identico.
rem
rem  O espelho e por pessoa (fica no %LOCALAPPDATA%), entao nao ha disputa entre
rem  instancias.
rem
rem  ── Como medir ────────────────────────────────────────────────────────────
rem
rem  A PRIMEIRA subida por aqui e fria de proposito: ela copia a arvore inteira
rem  e compila os ~313 modulos do zero (o cache de bytecode deste .bat e
rem  separado, `pycache-teste`, para nao se misturar com o de producao).  O
rem  numero que interessa e o da SEGUNDA em diante.
rem
rem  Compare `[TIME] entregando ao Python` contra `Serving on`, com o mesmo par
rem  do .bat de producao.
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
rem PRIMEIRO NUNCA VOLTA.  Vale para todo `ds` deste arquivo.
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

rem O %LOCALAPPDATA% e onde este .bat ja guarda o que precisa sobreviver ao
rem restart (a secret key, o snapshot do requirements, o bytecode).  Ele sobe
rem para ca -- antes ficava depois do pushd -- porque o espelho do codigo mora
rem nele e precisa existir ANTES.
set "APP_STATE_DIR=%LOCALAPPDATA%\OTC-Tracker"
if not exist "%APP_STATE_DIR%" mkdir "%APP_STATE_DIR%"

rem ---------------------------------------------------------------------------
rem  O ESPELHO LOCAL DO CODIGO -- a unica diferenca para o .bat de producao.
rem
rem  `src-teste` e nome proprio de proposito: o dia em que isto virar o padrao,
rem  a pasta muda de nome junto e ninguem fica com um espelho velho de teste
rem  sendo usado em producao sem perceber.
rem
rem  /MIR copia SO o que mudou e preserva os timestamps, entao o .pyc de um
rem  modulo que nao mudou continua valendo.  ATENCAO: /MIR tambem APAGA no
rem  destino o que nao existe na origem -- e por isso que o destino e uma pasta
rem  dedicada, e nunca deve apontar para outra coisa.
rem
rem  __pycache__ e .git ficam de fora: bytecode do share e de outra maquina e
rem  nao serve para nada aqui, e copia-lo so gasta tempo.
rem ---------------------------------------------------------------------------
set "SRC_LOCAL=%APP_STATE_DIR%\src-teste\%VERSION_PATH%"
echo Espelhando o codigo para o disco local... ^(a primeira vez demora^)
robocopy "%SHARE_ROOT%\otc-source\%VERSION_PATH%" "%SRC_LOCAL%" /MIR /XD __pycache__ .git /XF *.pyc /NFL /NDL /NJH /NJS /NP /R:2 /W:5

rem O robocopy devolve o codigo de saida em BITS: 0 = nada a copiar, 1 = copiou,
rem 2 = removeu extras, 3 = os dois... ate 7, e TODOS sao sucesso.  8 ou mais e
rem falha de verdade.  `if errorlevel 1` -- o teste natural -- abortaria toda vez
rem que a copia desse certo e tivesse copiado algo, que e o caso comum.
if errorlevel 8 (
    echo Error: Could not mirror the source to the local disk.
    exit /b 1
)

echo [TIME] codigo espelhado local    %TIME%

pushd "%SRC_LOCAL%" || exit /b 1
set "REQUIREMENTS_FILE=%SRC_LOCAL%\requirements.txt"

echo [TIME] rodando do disco local    %TIME%

rem Secret key persisted locally (never on the shared drive) so sessions
rem survive restarts without a hardcoded, guessable value sitting in a
rem script that everyone on the share can read.
set "SECRET_KEY_FILE=%APP_STATE_DIR%\secret_key.txt"
if not exist "%SECRET_KEY_FILE%" (
    %PYTHON_COMMAND% -c "import secrets; print(secrets.token_hex(32))" > "%SECRET_KEY_FILE%"
)
set /p "SECRET_KEY=" < "%SECRET_KEY_FILE%"

rem Skip both installs below when requirements.txt hasn't changed since the
rem last successful run. Pass --reinstall to force them (e.g. after the JPMC
rem package publishes an update).
rem
rem O snapshot e o MESMO do .bat de producao de proposito: a comparacao e de
rem CONTEUDO (`fc /b`), o requirements e o mesmo arquivo, e um snapshot proprio
rem so faria este .bat reinstalar tudo na primeira vez sem necessidade.
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
rem  Aqui o fonte JA esta em disco local, entao o prefixo deixou de ser o que
rem  evita gravar no share -- ele continua por DUAS razoes: manter o bytecode
rem  fora da arvore espelhada (o /MIR apagaria os __pycache__ a cada rodada, e
rem  tudo recompilaria) e nao misturar o cache deste .bat com o de producao, que
rem  falseia a medida.
rem
rem  `pycache-teste`, e nao `pycache`: os dois .bat rodam de caminhos de fonte
rem  diferentes, entao ja cairiam em subarvores diferentes do prefixo, mas com
rem  nomes separados da para APAGAR o do teste sem tocar no de producao.
rem ---------------------------------------------------------------------------
set "PYCACHE_DIR=%APP_STATE_DIR%\pycache-teste\%VERSION_PATH%"
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
