@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ============================================================================
REM  hotfix.bat - correcao pontual na versao que esta NO AR.
REM
REM  Compara este checkout com a pasta da versao apontada pelo link.txt e copia
REM  SO o que difere. Sem argumento apenas LISTA; "hotfix apply" copia.
REM
REM  Por que existe: a proxima versao e montada pelo new-otc-deploy.bat a partir
REM  DESTE checkout, nunca a partir da pasta que esta no share. Uma correcao
REM  feita direto na versao do share vive ate o proximo deploy e some sem aviso,
REM  porque o robocopy copia o arquivo antigo por cima. Entao a edicao nasce
REM  aqui e o hotfix a leva para la - os dois lados ficam iguais.
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
REM    __pycache__  - bytecode velho ao lado de fonte novo e ruido. O Python
REM                   recompila o modulo alterado sozinho na primeira subida.
REM    requirements.txt e os db.sqlite3 - dependencia nova nao e correcao
REM                   pontual: o snapshot de instalacao do start-otc-tracker.bat
REM                   e por VERSAO, entao so uma versao nova dispara o pip. O
REM                   script avisa quando o requirements mudou.
REM
REM  O destino sai do link.txt, nunca de um nome escrito aqui: quando a proxima
REM  versao subir, o comando continua certo sem ninguem lembrar de nada.
REM ============================================================================

set "SHARE_ROOT=\\NAWEST.ad.jpmorganchase.com\LAC\BRA\intra\Confirmation\Derivativos\OTC Tracker\Application"
set "SOURCE_ROOT=%~dp0apps"

REM Mesma lista branca do deploy, menos os bancos e o requirements.
set "DEPLOY_DIRS=pages static templates"
set "DEPLOY_FILES=__init__.py config.py run.py"
set "EXCLUDE_DIR=%SOURCE_ROOT%\static\data"

set "APPLY=0"
if /i "%~1"=="apply" set "APPLY=1"

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
type nul > "%LIST%"

echo.
echo Versao no ar : %VERSION%
echo Origem       : %SOURCE_ROOT%
echo Destino      : %TARGET%
echo.

REM --- Arquivos da raiz: sem /S e sem /E, robocopy pega so os nomeados. -------
robocopy "%SOURCE_ROOT%" "%TARGET%" %DEPLOY_FILES% /L /FP /NS /NC /NDL /NJH /NJS /NP >> "%LIST%"

REM --- Pastas: recursivo, sem o dado vivo e sem bytecode. ---------------------
for %%D in (%DEPLOY_DIRS%) do if exist "%SOURCE_ROOT%\%%D\" robocopy "%SOURCE_ROOT%\%%D" "%TARGET%\%%D" /E /L /FP /NS /NC /NDL /NJH /NJS /NP /XD "%EXCLUDE_DIR%" "__pycache__" >> "%LIST%"

set /a COUNT=0
set "FAIL="

for /f "usebackq tokens=* delims=" %%F in ("%LIST%") do call :considera "%%F"

echo.
if %COUNT%==0 (
    echo Nada a copiar - a versao no ar ja esta igual a este checkout.
    del "%LIST%" >nul 2>&1
    pause
    exit /b 0
)

if exist "%SOURCE_ROOT%\requirements.txt" if exist "%TARGET%\requirements.txt" (
    fc /b "%SOURCE_ROOT%\requirements.txt" "%TARGET%\requirements.txt" >nul 2>&1
    if errorlevel 1 (
        echo AVISO: requirements.txt mudou - o hotfix NAO instala dependencias.
        echo        Suba uma versao nova com o new-otc-deploy.bat.
    )
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

del "%LIST%" >nul 2>&1
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
set "SRC=%~1"
set "REL=!SRC:*%SOURCE_ROOT%\=!"
if "!REL!"=="!SRC!" goto :eof
set "SRC=%SOURCE_ROOT%\!REL!"
set /a COUNT+=1
echo    !REL!
if not "%APPLY%"=="1" goto :eof
set "DST=%TARGET%\!REL!"
set "BKF=%BACKUP%\!REL!"
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
