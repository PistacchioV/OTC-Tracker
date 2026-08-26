@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ============================================================================
REM  OTC Tracker - cria a proxima versao do codigo no share e aponta o link.txt.
REM
REM  A copia e uma LISTA BRANCA (DEPLOY_DIRS + DEPLOY_FILES): sobe o que esta
REM  listado, e so. Era um robocopy /E da pasta inteira, que levava junto tudo
REM  que estivesse na origem - inclusive a pasta static\data.
REM
REM  static\data NAO sobe: e o dado VIVO da instancia (os mappings editados pela
REM  tela, o DuckDB de usuarios, os caches por dia, os arquivos-dia do New
REM  Deals). Ele pertence a pasta que roda, e uma versao nova carregando a copia
REM  da maquina de desenvolvimento sobrescreveria o que a mesa cadastrou.
REM
REM  Pasta ou arquivo NOVO na aplicacao tem de entrar nas listas abaixo, senao a
REM  versao sobe sem ele. O script AVISA quando um item listado nao existe na
REM  origem (renomeado, movido) em vez de copiar menos em silencio.
REM ============================================================================

set "SHARE_ROOT=\\NAWEST.ad.jpmorganchase.com\LAC\BRA\intra\Confirmation\Derivativos\OTC Tracker\Application"
set "SCRIPT_ROOT=C:\JPMC\DEV\TMP\ds\OTCTracker"
set "SOURCE_ROOT=%SCRIPT_ROOT%\otc-source"
set "ORIGIN_PATH=%SOURCE_ROOT%"
set "CURRENT_VERSION_FILE=%SHARE_ROOT%\link.txt"

REM --- O que sobe -------------------------------------------------------------
set "DEPLOY_DIRS=pages static templates __pycache__"
set "DEPLOY_FILES=__init__.py config.py db.sqlite3 db.sqlite3.lock requirements.txt run.py"

REM --- O que fica de fora -----------------------------------------------------
REM  Por CAMINHO COMPLETO, de proposito: um /XD data casaria com QUALQUER pasta
REM  chamada data em qualquer nivel (as ha dentro de static\plugins), e a versao
REM  subiria sem pedacos de biblioteca. Para excluir mais de uma, repita o /XD
REM  na linha do robocopy - um par por pasta.
set "EXCLUDE_DIR=%ORIGIN_PATH%\static\data"

if not exist "%CURRENT_VERSION_FILE%" (
    echo Error: "%CURRENT_VERSION_FILE%" was not found.
    pause
    exit /b 1
)

set /p "CURRENT_VERSION=" < "%CURRENT_VERSION_FILE%"
if not defined CURRENT_VERSION (
    echo Error: link.txt does not contain a source version.
    pause
    exit /b 1
)

if not exist "%ORIGIN_PATH%\" (
    echo Error: Origin path "%ORIGIN_PATH%" was not found.
    pause
    exit /b 1
)

set /a HIGHEST_VERSION=0
for /d %%D in ("%SHARE_ROOT%\otc-source\v*") do (
    set "VERSION_NAME=%%~nxD"
    set "VERSION_NUMBER=!VERSION_NAME:~1!"
    for /f "delims=0123456789" %%A in ("!VERSION_NUMBER!") do set "VERSION_NUMBER="
    if defined VERSION_NUMBER if !VERSION_NUMBER! GTR !HIGHEST_VERSION! set /a HIGHEST_VERSION=VERSION_NUMBER
)

set /a NEXT_VERSION=HIGHEST_VERSION + 1
set "NEW_VERSION=v%NEXT_VERSION%"
set "TARGET_PATH=%SHARE_ROOT%\otc-source\%NEW_VERSION%"

if exist "%TARGET_PATH%\" (
    echo Error: Target version "%NEW_VERSION%" already exists.
    pause
    exit /b 1
)

REM --- Confere a lista contra a origem ANTES de copiar -------------------------
REM  Item listado que sumiu da origem nao derruba o deploy (o db.sqlite3.lock,
REM  por exemplo, so existe com a aplicacao rodando), mas tem de aparecer: a
REM  falha silenciosa aqui e uma versao no share sem uma pasta inteira.
set "MISSING="
for %%D in (%DEPLOY_DIRS%) do (
    if not exist "%ORIGIN_PATH%\%%D\" set "MISSING=!MISSING! %%D"
)
for %%F in (%DEPLOY_FILES%) do (
    if not exist "%ORIGIN_PATH%\%%F" set "MISSING=!MISSING! %%F"
)
if defined MISSING (
    echo Warning: not found in the source, NOT copied:!MISSING!
)

echo Copying "%ORIGIN_PATH%" to %NEW_VERSION%...

REM  Arquivos da raiz: sem /S e sem /E, entao robocopy copia SO os nomeados.
robocopy "%ORIGIN_PATH%" "%TARGET_PATH%" %DEPLOY_FILES% /COPY:DAT /R:2 /W:1 >nul
set "ROBOCOPY_RESULT=!ERRORLEVEL!"
if !ROBOCOPY_RESULT! GEQ 8 (
    echo Error: Copy failed for the root files. Robocopy returned !ROBOCOPY_RESULT!.
    echo        Partial version left at "%TARGET_PATH%" - remove it before retrying.
    pause
    exit /b !ROBOCOPY_RESULT!
)

for %%D in (%DEPLOY_DIRS%) do (
    if exist "%ORIGIN_PATH%\%%D\" (
        echo   - %%D
        robocopy "%ORIGIN_PATH%\%%D" "%TARGET_PATH%\%%D" /E /COPY:DAT /DCOPY:DAT /XD "%EXCLUDE_DIR%" /R:2 /W:1 >nul
        set "ROBOCOPY_RESULT=!ERRORLEVEL!"
        if !ROBOCOPY_RESULT! GEQ 8 (
            echo Error: Copy failed for "%%D". Robocopy returned !ROBOCOPY_RESULT!.
            echo        Partial version left at "%TARGET_PATH%" - remove it before retrying.
            pause
    exit /b !ROBOCOPY_RESULT!
        )
    )
)

echo Skipped: "%EXCLUDE_DIR%"

> "%CURRENT_VERSION_FILE%" echo %NEW_VERSION%
echo Created %NEW_VERSION% and updated link.txt.
pause
exit /b 0
