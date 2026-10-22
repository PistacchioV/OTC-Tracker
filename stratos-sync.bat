@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ============================================================================
REM  stratos-sync.bat - leva o OTC Tracker para o repositorio do Stratos.
REM
REM  O singing-moose-flask e o repositorio que o pipeline do Stratos constroi,
REM  e ele aponta para o Bitbucket: nao da para puxar do GitHub direto nele.
REM  Este script copia, deste checkout da branch OTC-Tracker-Stratos, o que
REM  DIFERE do destino:
REM
REM    apps\                     ->  <destino>\src\apps\
REM    stratos\src\*.py          ->  <destino>\src\    solution, run, otc_stratos
REM    stratos\requirements.txt  ->  <destino>\requirements.txt
REM
REM  Nada mais no destino e tocado: Dockerfile, terraform, Jenkinsfile, jules,
REM  tests\ e o favicon sao do template. Em src\apps o que nao existe mais aqui
REM  e REMOVIDO - a pasta e inteira do OTC, e um modulo apagado na dev nao pode
REM  continuar no servidor.
REM
REM  Sem argumento apenas LISTA; "stratos-sync apply" copia. Antes, o script:
REM    1. atualiza este checkout - git pull - e confere a branch e que ele nao
REM       tem nada fora do git em apps\ ou stratos\: o servidor tem de receber
REM       a branch, nao o que alguem deixou na pasta;
REM    2. confere que o destino e um repositorio git e o poe na ramificacao
REM       do Stratos CLI, feature/stratos - DEST_BRANCH abaixo, ou a variavel
REM       OTC_STRATOS_BRANCH. Fora dela o CLI nao reconhece o projeto.
REM  Depois do apply, no destino: stratos status e stratos push "mensagem".
REM
REM  "Diferente" e data ou tamanho, como no hotfix.bat: um git pull troca a
REM  data so dos arquivos que mudaram, e so eles sao copiados.
REM
REM  Fica de fora static\data\cache: dia de exemplo da dev, que o servidor
REM  importaria para o banco dele na primeira subida. As sementes - mappings,
REM  RefData, traducoes, templates do File Interpreter - vao.
REM
REM  Uma vez por maquina, de dentro do clone do OTC Tracker:
REM    git worktree add ..\OTC-Tracker-Stratos OTC-Tracker-Stratos
REM  e rode este .bat de la.
REM ============================================================================

set "SRC_BRANCH=OTC-Tracker-Stratos"
set "DEST=%USERPROFILE%\ds\python-solutions\stratos\76521\singing-moose-flask"
if defined OTC_STRATOS_DEST set "DEST=%OTC_STRATOS_DEST%"
REM Barra no fim viraria aspas escapadas no robocopy: "C:\x\" .
if "%DEST:~-1%"=="\" set "DEST=%DEST:~0,-1%"
set "DEST_BRANCH=feature/stratos"
if defined OTC_STRATOS_BRANCH set "DEST_BRANCH=%OTC_STRATOS_BRANCH%"

set "REPO=%~dp0"
if "%REPO:~-1%"=="\" set "REPO=%REPO:~0,-1%"
set "APPS_SRC=%REPO%\apps"
set "APPS_DST=%DEST%\src\apps"
set "OVL_SRC=%REPO%\stratos\src"
set "OVL_DST=%DEST%\src"

set "APPLY=0"
if /i "%~1"=="apply" set "APPLY=1"

REM O pull vem PRIMEIRO e dentro de um bloco. O cmd le o .bat do disco aos
REM poucos, e um pull que mude ESTE arquivo no meio da execucao faria o resto
REM ser lido no deslocamento antigo do arquivo novo - comandos pela metade. O
REM bloco e lido inteiro antes de rodar; depois do pull o script chama a si
REM mesmo, ja na versao nova, e esta copia termina sem ler mais nada do disco.
if not defined OTC_STRATOS_PULLED (
    set "OTC_STRATOS_PULLED=1"
    echo Atualizando este checkout ...
    git -C "%REPO%" pull --ff-only
    if errorlevel 1 set "OTC_STRATOS_PULL_FALHOU=1"
    call "%~f0" %*
    goto :eof
)

where git >nul 2>&1
if errorlevel 1 (
    echo Erro: git nao encontrado no PATH.
    pause
    exit /b 1
)

REM --- 1. Este checkout: a branch certa, atualizada e limpa. -----------------
set "CUR_SRC="
for /f "delims=" %%B in ('git -C "%REPO%" rev-parse --abbrev-ref HEAD 2^>nul') do set "CUR_SRC=%%B"
if /i not "%CUR_SRC%"=="%SRC_BRANCH%" (
    echo Erro: este checkout esta na branch "%CUR_SRC%", e o que vai para o
    echo       Stratos e a %SRC_BRANCH%. Rode este .bat da worktree dela.
    pause
    exit /b 1
)

if defined OTC_STRATOS_PULL_FALHOU (
    echo AVISO: o git pull falhou - a lista abaixo e do que ja estava aqui.
    if "%APPLY%"=="1" (
        echo Corrija o checkout antes do apply.
        pause
        exit /b 1
    )
)

set "SUJO=0"
for /f "delims=" %%L in ('git -C "%REPO%" status --porcelain --ignored -- apps stratos ^| findstr /v /i /l "__pycache__ .pyc"') do (
    if "!SUJO!"=="0" echo AVISO: fora do git neste checkout - nao iria para o servidor:
    set "SUJO=1"
    echo    %%L
)
if "%SUJO%"=="1" if "%APPLY%"=="1" (
    echo Limpe o checkout antes do apply - git status, git clean -ndX.
    pause
    exit /b 1
)

REM --- 2. O destino: repositorio git, na ramificacao certa. -----------------
if not exist "%DEST%\" (
    echo Erro: destino "%DEST%" nao encontrado.
    echo       Ajuste DEST no topo deste .bat ou a variavel OTC_STRATOS_DEST.
    pause
    exit /b 1
)
git -C "%DEST%" rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    echo Erro: "%DEST%" nao e um repositorio git.
    pause
    exit /b 1
)
set "CUR_DEST="
for /f "delims=" %%B in ('git -C "%DEST%" rev-parse --abbrev-ref HEAD 2^>nul') do set "CUR_DEST=%%B"
if /i not "%CUR_DEST%"=="%DEST_BRANCH%" (
    if "%APPLY%"=="0" (
        echo AVISO: o destino esta na ramificacao "%CUR_DEST%" - o apply troca para "%DEST_BRANCH%".
    ) else (
        echo Trocando o destino de "%CUR_DEST%" para "%DEST_BRANCH%" ...
        git -C "%DEST%" checkout "%DEST_BRANCH%"
        if errorlevel 1 (
            echo Erro: nao consegui trocar de ramificacao - commit ou stash no destino antes.
            pause
            exit /b 1
        )
        set "CUR_DEST=%DEST_BRANCH%"
    )
)

REM --- 3. O que difere. ------------------------------------------------------
set "LIST=%TEMP%\otc-stratos-apps.txt"
set "OLIST=%TEMP%\otc-stratos-src.txt"
set "RLIST=%TEMP%\otc-stratos-req.txt"
set "XLIST=%TEMP%\otc-stratos-extra.txt"
type nul > "%LIST%"
type nul > "%OLIST%"
type nul > "%RLIST%"
type nul > "%XLIST%"

REM As duas pontas do cache entram no /XD: a de origem para nao copiar, a de
REM destino para o que estiver la nao virar "removido".
set XD=__pycache__ "%APPS_SRC%\static\data\cache" "%APPS_DST%\static\data\cache"
set XF=*.pyc *.pyo *.bak *.dev-backup

robocopy "%APPS_SRC%" "%APPS_DST%" /E /L /FP /NS /NC /NDL /NJH /NJS /NP /XD %XD% /XF %XF% >> "%LIST%"
if errorlevel 8 (
    echo Erro: o robocopy falhou ao comparar apps - confira os caminhos acima.
    pause
    exit /b 1
)
robocopy "%OVL_SRC%" "%OVL_DST%" *.py /L /FP /NS /NC /NDL /NJH /NJS /NP >> "%OLIST%"
robocopy "%REPO%\stratos" "%DEST%" requirements.txt /L /FP /NS /NC /NDL /NJH /NJS /NP >> "%RLIST%"

REM Sobrando no destino: com /X o robocopy lista o que so existe la, e os /XC
REM /XN /XO /XL tiram da lista tudo o mais - o que mudou e o que e novo.
if exist "%APPS_DST%\" robocopy "%APPS_SRC%" "%APPS_DST%" /E /L /X /XC /XN /XO /XL /FP /NS /NDL /NJH /NJS /NP /XD %XD% /XF %XF% >> "%XLIST%"

echo.
echo Origem  : %REPO%  [%SRC_BRANCH%]
echo Destino : %DEST%  [%CUR_DEST%]
echo.

set /a COUNT=0
set /a XCOUNT=0
set "FAIL="
set "REQ="

for /f "usebackq tokens=* delims=" %%F in ("%LIST%") do call :considera "%%F" "%APPS_SRC%" "%APPS_DST%" "src\apps\"
for /f "usebackq tokens=* delims=" %%F in ("%OLIST%") do call :considera "%%F" "%OVL_SRC%" "%OVL_DST%" "src\"
for /f "usebackq tokens=* delims=" %%F in ("%RLIST%") do (
    set "REQ=1"
    call :considera "%%F" "%REPO%\stratos" "%DEST%" ""
)
for /f "usebackq tokens=* delims=" %%F in ("%XLIST%") do (
    echo %%F | findstr /l /c:"EXTRA File" >nul && call :remove "%%F" "%APPS_DST%" "src\apps\"
)

del "%LIST%" "%OLIST%" "%RLIST%" "%XLIST%" >nul 2>&1
echo.
set /a TOTAL=COUNT+XCOUNT
if %TOTAL%==0 (
    echo Nada a fazer - o destino ja esta igual a %SRC_BRANCH%.
    pause
    exit /b 0
)

if defined REQ echo AVISO: requirements.txt mudou - o pipeline reinstala; no venv local do destino, pip install -r requirements.txt.

if "%APPLY%"=="0" (
    echo %COUNT% para copiar, %XCOUNT% para remover. Para aplicar, rode:  stratos-sync apply
) else (
    if defined FAIL (
        echo ATENCAO: houve erro em pelo menos um arquivo - confira a lista acima.
    ) else (
        echo %COUNT% copiado[s], %XCOUNT% removido[s] em %DEST%.
        echo Agora, no destino: stratos status e stratos push "mensagem".
    )
)
echo.
pause
exit /b 0

REM ============================================================================
REM  Sub-rotinas. Ficam depois do exit para nao rodarem na sequencia - e existem
REM  para o mkdir do pai poder usar %~dp1: dentro de um bloco ( ... ) isso pediria
REM  um for aninhado, e parentese dentro de bloco e onde o cmd quebra calado.
REM ============================================================================

:considera
REM A linha vem do robocopy em modo lista, ALINHADA em colunas: o caminho chega
REM com tabs e espacos na frente. O replace com * corta tudo ate a raiz, e o SRC
REM e remontado pela raiz pelo mesmo motivo - o mesmo cuidado do hotfix.bat.
REM %1 a linha, %2 raiz de origem, %3 raiz de destino, %4 prefixo exibido.
set "SRC=%~1"
set "SROOT=%~2"
set "DROOT=%~3"
set "SHOW=%~4"
set "REL=!SRC:*%SROOT%\=!"
if "!REL!"=="!SRC!" goto :eof
set "SRC=!SROOT!\!REL!"
set /a COUNT+=1
echo    !SHOW!!REL!
if not "%APPLY%"=="1" goto :eof
set "DST=!DROOT!\!REL!"
call :garante_pasta "!DST!"
copy /y "!SRC!" "!DST!" >nul
if errorlevel 1 (
    echo       ERRO ao copiar !REL!
    set "FAIL=1"
)
goto :eof

:remove
REM %1 a linha "*EXTRA File" do robocopy, %2 raiz do destino, %3 prefixo exibido.
set "LIN=%~1"
set "DROOT=%~2"
set "SHOW=%~3"
set "REL=!LIN:*%DROOT%\=!"
if "!REL!"=="!LIN!" goto :eof
set /a XCOUNT+=1
echo  - !SHOW!!REL!
if not "%APPLY%"=="1" goto :eof
del /f /q "!DROOT!\!REL!" >nul 2>&1
if exist "!DROOT!\!REL!" (
    echo       ERRO ao remover !REL!
    set "FAIL=1"
)
goto :eof

:garante_pasta
if not exist "%~dp1" mkdir "%~dp1" >nul 2>&1
goto :eof
