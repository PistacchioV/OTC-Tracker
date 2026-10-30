@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ============================================================================
REM  hotfix.bat - correcao pontual na versao que esta NO AR.
REM
REM  Compara este checkout com a pasta da versao apontada pelo link.txt e copia
REM  SO o que difere. Sem argumento apenas LISTA; "hotfix apply" copia.
REM
REM  Num .bat so, como o stratos-sync.bat (26/10/2026): antes de comparar ele
REM    1. ATUALIZA este checkout do GitHub - git pull --ff-only. Era um passo a
REM       mao, e esquecido o hotfix comparava o checkout velho com a versao no
REM       ar e dizia "nada a copiar" com a correcao ja no repositorio;
REM    2. confere a branch - StreamFlow-prod, BRANCH abaixo: e ela que tem o
REM       config.py da instancia; de outra branch iriam os caminhos da dev;
REM    3. confere que apps\ nao tem nada fora do git: o robocopy copia o que
REM       estiver na pasta, e a versao no ar tem de receber a branch, nao uma
REM       sobra local. O dado de static\data fica de fora da conferencia, como
REM       fica do hotfix - menos as traducoes, que vao.
REM  Pull que falha ou checkout sujo: lista, mas o apply RECUSA.
REM
REM  Por que existe: a proxima versao e montada pelo new-otc-deploy.bat a partir
REM  DESTE checkout, nunca a partir da pasta que esta no share. Uma correcao
REM  feita direto na versao do share vive ate o proximo deploy e some sem aviso,
REM  porque o robocopy copia o arquivo antigo por cima. Entao a correcao nasce
REM  no REPOSITORIO - na dev, e chega a StreamFlow-prod pelo merge - e o hotfix
REM  a puxa do GitHub e a leva para la: os dois lados ficam iguais.
REM
REM  "Alterado" e o que DIFERE do que esta no ar, nao o que foi salvo nas
REM  ultimas N horas: o robocopy compara data e tamanho contra a pasta da
REM  versao. Funciona igual para uma edicao de agora e para um git pull de tres
REM  dias atras, e nao copia o que ja esta identico.
REM
REM  Fica de fora, de proposito:
REM    static\data  - o dado VIVO da instancia: os mappings editados pela tela,
REM                   os caches por dia, os arquivos-dia. Mesma exclusao que o
REM                   new-otc-deploy.bat faz, e pela mesma razao.
REM                   MENOS static\data\translations: a i18n e CODIGO
REM                   versionado, nao dado da mesa, e a instancia a le do
REM                   DATA_DIR (Application\static\data), nao da pasta da
REM                   versao. Sem esta passada propria, texto novo de tela
REM                   chegava com o hotfix e aparecia em ingles/sem traducao.
REM    __pycache__  - bytecode velho ao lado de fonte novo e ruido. O Python
REM                   recompila o modulo alterado sozinho na primeira subida.
REM
REM  O requirements.txt VAI (29/10/2026): ele mora na RAIZ do repositorio,
REM  nao em apps\, e tem passada propria (ROOT_FILES). O
REM  start-otc-tracker.bat compara o requirements.txt da versao com o retrato
REM  da ultima instalacao (fc /b), entao o requirements que chega pelo hotfix
REM  dispara o pip install na PROXIMA subida, sozinho - o script avisa.
REM
REM  O GUIA_DO_USUARIO_OTC_TRACKER.docx VAI (30/10/2026), tambem da RAIZ do
REM  repositorio, mas para a pasta otc-source - ao lado das pastas de versao,
REM  onde a equipe o abre -, e nao para dentro da versao. A comparacao e pelo
REM  CONTEUDO (fc /b), nao pela data: o git pull e o clone novo mudam a data do
REM  arquivo sem mudar o guia, e ele seria copiado a cada vez.
REM
REM  O run.py NUNCA vai: o da pasta da versao e PROPRIO da instancia (mora ao
REM  lado do __init__.py e do config.py, sem o pacote apps) e o do repositorio
REM  faz "from apps.config import" - copiado por cima, a instancia nao sobe
REM  para ninguem (ModuleNotFoundError: No module named 'apps', 29/10/2026).
REM
REM  O destino sai do link.txt, nunca de um nome escrito aqui: quando a proxima
REM  versao subir, o comando continua certo sem ninguem lembrar de nada.
REM ============================================================================

set "SHARE_ROOT=\\NAWEST.ad.jpmorganchase.com\LAC\BRA\intra\Confirmation\Derivativos\OTC Tracker\Application"
set "SOURCE_ROOT=%~dp0apps"
set "BRANCH=StreamFlow-prod"
if defined OTC_HOTFIX_BRANCH set "BRANCH=%OTC_HOTFIX_BRANCH%"
set "REPO=%~dp0"
if "%REPO:~-1%"=="\" set "REPO=%REPO:~0,-1%"

REM Mesma lista branca do deploy, menos o __pycache__. Os arquivos de apps\ e
REM os da RAIZ do repositorio vao separados: na pasta da versao todos ficam lado
REM a lado, mas aqui o requirements.txt nao mora em apps\. O run.py fica de
REM FORA: o da versao e outro arquivo (ver o cabecalho).
set "DEPLOY_DIRS=pages static templates"
set "DEPLOY_FILES=__init__.py config.py"
set "ROOT_FILES=requirements.txt"
set "EXCLUDE_DIR=%SOURCE_ROOT%\static\data"

REM O guia do usuario: da raiz do repositorio para a pasta otc-source do share.
set "GUIDE=GUIA_DO_USUARIO_OTC_TRACKER.docx"
set "GUIDE_DST=%SHARE_ROOT%\otc-source"

REM A i18n vai para o DATA_DIR da instancia, que e onde o app a procura primeiro
REM (static_data_file: data_dir() antes da copia empacotada).
set "TRANS_SRC=%SOURCE_ROOT%\static\data\translations"
set "TRANS_DST=%SHARE_ROOT%\static\data\translations"

set "APPLY=0"
if /i "%~1"=="apply" set "APPLY=1"

where git >nul 2>&1
if errorlevel 1 (
    echo Erro: git nao encontrado no PATH - abra o .bat de dentro do DevShell.
    pause
    exit /b 1
)

REM --- 0. Atualizar este checkout ANTES de comparar. -------------------------
REM O pull vem dentro de um bloco. O cmd le o .bat do disco aos poucos, e um
REM pull que mude ESTE arquivo no meio da execucao faria o resto ser lido no
REM deslocamento antigo do arquivo novo - comandos pela metade. O bloco e lido
REM inteiro antes de rodar; depois do pull o script chama a si mesmo, ja na
REM versao nova, e esta copia termina sem ler mais nada do disco. E o mesmo
REM desenho do stratos-sync.bat.
if not defined OTC_HOTFIX_PULLED (
    set "OTC_HOTFIX_PULLED=1"
    echo Atualizando este checkout do GitHub ...
    git -C "%REPO%" pull --ff-only
    if errorlevel 1 set "OTC_HOTFIX_PULL_FALHOU=1"
    call "%~f0" %*
    goto :eof
)

REM --- 1. A branch certa, atualizada e sem sobra fora do git. ----------------
set "CUR="
for /f "delims=" %%B in ('git -C "%REPO%" rev-parse --abbrev-ref HEAD 2^>nul') do set "CUR=%%B"
if /i not "%CUR%"=="%BRANCH%" (
    echo Erro: este checkout esta na branch "%CUR%", e o hotfix leva a %BRANCH%
    echo       para a versao no ar - a branch com o config.py da instancia.
    pause
    exit /b 1
)

if defined OTC_HOTFIX_PULL_FALHOU (
    echo AVISO: o git pull falhou - a lista abaixo e do que ja estava aqui.
    if "%APPLY%"=="1" (
        echo Corrija o checkout antes do apply - git status, git pull.
        pause
        exit /b 1
    )
)

set "SUJO=0"
for /f "delims=" %%L in ('git -C "%REPO%" status --porcelain --ignored -- apps %ROOT_FILES% %GUIDE% ^| findstr /v /i /l "__pycache__ .pyc"') do call :sujo "%%L"
if "%SUJO%"=="1" if "%APPLY%"=="1" (
    echo Limpe o checkout antes do apply - git status, git clean -ndX.
    pause
    exit /b 1
)

if not exist "%SOURCE_ROOT%\" (
    echo Error: source "%SOURCE_ROOT%" was not found.
    pause
    exit /b 1
)

set "VERSION_FILE=%SHARE_ROOT%\link.txt"
if not exist "%VERSION_FILE%" (
    echo Error: "%VERSION_FILE%" was not found.
    pause
    exit /b 1
)

set /p "VERSION=" < "%VERSION_FILE%"
if not defined VERSION (
    echo Error: link.txt does not contain a source version.
    pause
    exit /b 1
)

set "TARGET=%SHARE_ROOT%\otc-source\%VERSION%"
if not exist "%TARGET%\" (
    echo Error: version "%VERSION%" was not found at "%TARGET%".
    pause
    exit /b 1
)

set "BACKUP=%LOCALAPPDATA%\OTC-Tracker\hotfix-backup\%VERSION%"
set "LIST=%TEMP%\otc-hotfix-list.txt"
set "TLIST=%TEMP%\otc-hotfix-translations.txt"
set "RLIST=%TEMP%\otc-hotfix-root.txt"
type nul > "%LIST%"
type nul > "%TLIST%"
type nul > "%RLIST%"

echo.
echo Versao no ar : %VERSION%
echo Origem       : %SOURCE_ROOT%  [%BRANCH%]
echo Destino      : %TARGET%
echo.

REM --- Arquivos da raiz: sem /S e sem /E, robocopy pega so os nomeados. -------
robocopy "%SOURCE_ROOT%" "%TARGET%" %DEPLOY_FILES% /L /FP /NS /NC /NDL /NJH /NJS /NP >> "%LIST%"

REM --- Arquivo da raiz do repositorio: o requirements.txt. --------------------
robocopy "%REPO%" "%TARGET%" %ROOT_FILES% /L /FP /NS /NC /NDL /NJH /NJS /NP >> "%RLIST%"

REM --- Pastas: recursivo, sem o dado vivo e sem bytecode. ---------------------
for %%D in (%DEPLOY_DIRS%) do if exist "%SOURCE_ROOT%\%%D\" robocopy "%SOURCE_ROOT%\%%D" "%TARGET%\%%D" /E /L /FP /NS /NC /NDL /NJH /NJS /NP /XD "%EXCLUDE_DIR%" "__pycache__" >> "%LIST%"

REM --- Traducoes: destino proprio, o DATA_DIR da instancia. -----------------
if exist "%TRANS_SRC%\" robocopy "%TRANS_SRC%" "%TRANS_DST%" *.json /L /FP /NS /NC /NDL /NJH /NJS /NP >> "%TLIST%"

set /a COUNT=0
set "FAIL="

REM Conferido ANTES da copia: depois do apply os dois ficam iguais.
set "REQ_MUDOU="
if exist "%REPO%\requirements.txt" (
    fc /b "%REPO%\requirements.txt" "%TARGET%\requirements.txt" >nul 2>&1
    if errorlevel 1 set "REQ_MUDOU=1"
)

for /f "usebackq tokens=* delims=" %%F in ("%LIST%") do call :considera "%%F" "%SOURCE_ROOT%" "%TARGET%" "%BACKUP%" ""
for /f "usebackq tokens=* delims=" %%F in ("%RLIST%") do call :considera "%%F" "%REPO%" "%TARGET%" "%BACKUP%" ""
for /f "usebackq tokens=* delims=" %%F in ("%TLIST%") do call :considera "%%F" "%TRANS_SRC%" "%TRANS_DST%" "%BACKUP%\_data-translations" "static\data\translations\"

REM --- O guia do usuario: pelo CONTEUDO, para a pasta otc-source. -----------
REM fc /b devolve 1 se difere e 2 se o do share nao existe - os dois copiam.
if exist "%REPO%\%GUIDE%" (
    fc /b "%REPO%\%GUIDE%" "%GUIDE_DST%\%GUIDE%" >nul 2>&1
    if errorlevel 1 call :considera "%REPO%\%GUIDE%" "%REPO%" "%GUIDE_DST%" "%BACKUP%\_otc-source" "otc-source\"
)

echo.
if %COUNT%==0 (
    echo Nada a copiar - a versao no ar ja esta igual a este checkout.
    del "%LIST%" "%TLIST%" "%RLIST%" >nul 2>&1
    pause
    exit /b 0
)

if defined REQ_MUDOU (
    echo AVISO: o requirements.txt mudou - a proxima subida do start-otc-tracker.bat
    echo        roda o pip install sozinha, e por isso demora mais.
)

if "%APPLY%"=="0" (
    echo %COUNT% arquivo^(s^) diferente^(s^). Para copiar, rode:  hotfix apply
) else (
    if defined FAIL (
        echo ATENCAO: houve erro em pelo menos um arquivo - confira a lista acima.
    ) else (
        echo %COUNT% arquivo^(s^) copiado^(s^) para %VERSION%.
        echo Backup do original em: %BACKUP%
        echo REINICIE o app - o reloader esta desligado e o codigo velho segue servindo.
    )
)

del "%LIST%" "%TLIST%" "%RLIST%" >nul 2>&1
echo.
pause
exit /b 0

REM ============================================================================
REM  Sub-rotinas. Ficam depois do exit para nao serem executadas na sequencia.
REM  Elas existem para o mkdir do diretorio-pai poder usar %~dp1: dentro de um
REM  bloco ( ... ) isso exigiria um for aninhado, e parentese dentro de bloco e
REM  onde o cmd quebra em silencio.
REM ============================================================================

:considera
REM A linha vem do robocopy em modo lista, e ele ALINHA a saida em colunas: o
REM caminho chega precedido de tabs e espacos. O for /f la em cima esta com
REM delims= VAZIO de proposito (nome de arquivo pode ter espaco), entao ele nao
REM apara nada - quem tem de aparar e aqui. A forma com * do replace remove tudo
REM ate a primeira ocorrencia INCLUSIVE, e nao so a ocorrencia, que e o que
REM deixava o preenchimento na frente do relativo: o destino virava
REM "...\v15\<tabs>pages\routes.py" e o Windows respondia "The filename,
REM directory name, or volume label syntax is incorrect" uma vez por arquivo.
REM O SRC e remontado da raiz pelo mesmo motivo - ele carrega o mesmo lixo.
REM Argumentos: %1 a linha do robocopy, %2 raiz de origem, %3 raiz de destino,
REM %4 raiz do backup, %5 prefixo so para exibir (as traducoes nao moram sob
REM a pasta da versao, e a lista tem de dizer de onde cada arquivo e).
set "SRC=%~1"
set "SROOT=%~2"
set "DROOT=%~3"
set "BROOT=%~4"
set "SHOW=%~5"
set "REL=!SRC:*%SROOT%\=!"
if "!REL!"=="!SRC!" goto :eof
set "SRC=!SROOT!\!REL!"
set /a COUNT+=1
echo    !SHOW!!REL!
if not "%APPLY%"=="1" goto :eof
set "DST=!DROOT!\!REL!"
set "BKF=!BROOT!\!REL!"
REM O backup guarda o arquivo COMO FOI IMPLANTADO: so grava se ainda nao houver
REM copia, senao o segundo hotfix no mesmo arquivo apagaria o original.
if not exist "!BKF!" if exist "!DST!" call :garante_pasta "!BKF!"
if not exist "!BKF!" if exist "!DST!" copy /y "!DST!" "!BKF!" >nul
call :garante_pasta "!DST!"
copy /y "!SRC!" "!DST!" >nul
if errorlevel 1 (
    echo       ERRO ao copiar !REL!
    set "FAIL=1"
)
goto :eof

:garante_pasta
if not exist "%~dp1" mkdir "%~dp1" >nul 2>&1
goto :eof

:sujo
REM %1 uma linha do git status --porcelain --ignored. O que mora em
REM apps\static\data e dado da instancia e o hotfix nao leva - nao conta -,
REM menos as traducoes, que ele leva e por isso contam. O teste e por
REM substituicao: a linha muda quando o trecho esta nela.
set "LIN=%~1"
set "T1=!LIN:apps/static/data/=!"
set "T2=!LIN:apps/static/data/translations/=!"
if not "!T1!"=="!LIN!" if "!T2!"=="!LIN!" goto :eof
if "!SUJO!"=="0" echo AVISO: fora do git neste checkout - nao iria para a versao no ar:
set "SUJO=1"
echo    !LIN!
goto :eof
