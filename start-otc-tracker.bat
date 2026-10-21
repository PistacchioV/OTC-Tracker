@echo off
setlocal
rem Quem chama pode se apresentar: o start-otc-tracker_naeast.bat e um
rem LANCADOR deste arquivo, com nome e atalho proprios.
if not defined OTC_NOME set "OTC_NOME=OTC Tracker"
if not defined OTC_LAUNCHER set "OTC_LAUNCHER=%~f0"
title %OTC_NOME%

rem ===========================================================================
rem  OTC Tracker - subida da instancia (o .bat que mora no SHARE, na pasta
rem  Application).  DUPLO CLIQUE e pronto: NAO precisa do DevShell.
rem
rem  O que o DevShell dava, e o que este .bat faz no lugar (08/10/2026):
rem
rem   - o Python do `ds tool install`: o app roda no 3.13 e no 3.12 (HANDOFF
rem     651/652), e o .bat procura o 3.13 PRIMEIRO e, sem ele, o 3.12 -- quem
rem     ja sobe pelo 3.12 continua nele.  Em cada versao, o Python PROPRIO do
rem     OTC Tracker em %LOCALAPPDATA%\OTC-Tracker\python313 (ou python312) e,
rem     sem ele, um ja instalado para o usuario.  Sem nenhum dos dois, instala
rem     o 3.13 so para este usuario, sem admin; sem o instalador do 3.13, o do
rem     3.12.  O instalador sai da pasta installers ao lado deste .bat no
rem     share, sem internet, ou do python.org pelo proxy do sistema.  So roda
rem     se for um instalador ASSINADO: uma pagina de bloqueio do proxy salva
rem     com o nome do .exe nunca e executada.
rem   - o pip configurado: PIP_INDEX_URL no Artifactory, o mesmo de onde o
rem     awmpy sempre veio, a nao ser que a maquina ja defina outro.
rem   - o localproxy-cfg: nao e instalado.  O app nao depende dele -- o Quotes
rem     tenta o proxy do sistema e as Tools caem para o WinHTTP, CLAUDE.md 9.
rem
rem  O Python proprio NAO entra no PATH e nao mexe em outro Python da maquina:
rem  quem roda o app e sempre o %%PY%% abaixo.  Para forcar a reinstalacao das
rem  dependencias:  start-otc-tracker.bat --reinstall
rem
rem  Quando o servidor responde, o navegador abre sozinho em localhost:8051.
rem
rem  Na primeira vez numa maquina ele poe o atalho "OTC Tracker" no Desktop e,
rem  se ainda nao houver, na pasta Application do share, com o icone
rem  otc-tracker.ico que mora ao lado dele.  O .bat em si nao tem icone -- o
rem  Windows desenha o mesmo para todo .bat --, e o atalho resolve tres coisas:
rem  o icone, o FIXAR na barra de tarefas e no Iniciar, que o Windows recusa
rem  para atalho de .bat e aceita para o cmd.exe que o chama, e o aviso
rem  "UNC paths are not supported" do topo da janela, porque o atalho abre
rem  com uma pasta LOCAL como diretorio atual.  Apagado do Desktop, nao volta.
rem
rem  O ESPELHO LOCAL do codigo (OTC_ESPELHO_LOCAL=1) e o que o
rem  start-otc-tracker_naeast.bat liga: o codigo da versao e copiado para o
rem  disco local antes de subir.  Ver a sub-rotina :espelha.
rem ===========================================================================

echo [TIME] inicio do .bat            %TIME%

set "SHARE_ROOT=\\NAWEST.ad.jpmorganchase.com\LAC\BRA\intra\Confirmation\Derivativos\OTC Tracker\Application"
set "APP_STATE_DIR=%LOCALAPPDATA%\OTC-Tracker"
rem As duas versoes que o app aceita, na ordem em que sao procuradas, com o
rem instalador EXATO que o .bat poe na pasta propria de cada uma.
set "PY313_VERSION=3.13.14"
set "PY312_VERSION=3.12.10"
if not defined OTC_PYTHON_FTP set "OTC_PYTHON_FTP=https://www.python.org/ftp/python"
set "PY="
set "ARTIFACTORY_PYPI=https://artifacts.jpmchase.net/artifactory/api/pypi/pypi/simple/"
if not defined PIP_INDEX_URL set "PIP_INDEX_URL=%ARTIFACTORY_PYPI%"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "PIP_NO_INPUT=1"
set "PIP_NO_WARN_SCRIPT_LOCATION=1"
set "PUSHED="

if not exist "%APP_STATE_DIR%" mkdir "%APP_STATE_DIR%"

rem Os atalhos: uma vez por maquina e por lancador, marcada pelo arquivo
rem "atalho <nome>.ok" -- quem apagou o do Desktop decidiu nao te-lo.  O icone
rem do Desktop e COPIADO para o disco local, para o atalho nao ficar sem
rem desenho quando o share demora a responder; o do share usa o do share,
rem porque serve a todas as maquinas.
set "ICON=%APP_STATE_DIR%\otc-tracker.ico"
set "ICON_SHARE=%~dp0otc-tracker.ico"
set "LNK_SHARE=%~dp0%OTC_NOME%.lnk"
if not exist "%ICON%" if exist "%ICON_SHARE%" copy /y "%ICON_SHARE%" "%ICON%" >nul
if not exist "%APP_STATE_DIR%\atalho %OTC_NOME%.ok" if exist "%ICON%" call :cria_atalho

rem O Python: o 3.13 e, sem ele, o 3.12 -- em cada um, o proprio, o instalado
rem para o usuario e o do PATH, que e o do DevShell.  Sem nenhum, instala o
rem 3.13; se o instalador dele nao vier (nem do share, nem do download), o
rem 3.12.  Uma maquina que ja sobe pelo 3.12 so muda quando ganhar um 3.13.
rem
rem A politica de grupo do JPM BARRA o instalador do python.org em parte das
rem maquinas ("This program is blocked by group policy", 21/10/2026): ali o
rem Python vem do DevShell -- `ds tool install python3.12`, o caminho liberado
rem pela TI e o que o .bat usava antes do HANDOFF 628 --, e o .bat o acha no
rem PATH.  Fora do DevShell o PATH pode nao te-lo: OTC_PYTHON com o caminho do
rem python.exe vence toda a busca (uma vez por usuario: setx OTC_PYTHON "...").
set "ERRO=Nao consegui instalar o Python %PY313_VERSION% nem o %PY312_VERSION% - os motivos estao nos avisos acima. Se o Windows disse 'blocked by group policy', esta maquina nao deixa rodar o instalador: instale o Python pelo DevShell - ds tool install python3.12 - e abra este .bat de dentro do DevShell, ou grave uma vez o caminho do python.exe com: setx OTC_PYTHON seguido do caminho - e abra de novo."
if defined OTC_PYTHON if exist "%OTC_PYTHON%" set "PY=%OTC_PYTHON%"
if defined OTC_PYTHON if not defined PY echo [AVISO] OTC_PYTHON aponta para "%OTC_PYTHON%", que nao existe - procurando outro Python.
if not defined PY call :acha_python 3.13
if not defined PY call :acha_python 3.12
if not defined PY call :instala_python %PY313_VERSION% 3.13
if not defined PY call :instala_python %PY312_VERSION% 3.12
if not defined PY goto :falha
echo [INFO] Python: %PY%
"%PY%" --version
echo [TIME] python conferido          %TIME%

set "ERRO=Nao consegui ler a versao em %SHARE_ROOT%\link.txt"
set "VERSION_PATH="
set /p "VERSION_PATH=" < "%SHARE_ROOT%\link.txt"
if not defined VERSION_PATH goto :falha

set "CODIGO=%SHARE_ROOT%\otc-source\%VERSION_PATH%"
set "PYCACHE_DIR=%APP_STATE_DIR%\pycache\%VERSION_PATH%"
if defined OTC_ESPELHO_LOCAL call :espelha
if defined OTC_ESPELHO_LOCAL if not defined ESPELHO_OK goto :falha

set "ERRO=Nao consegui abrir a pasta do codigo: %CODIGO%"
pushd "%CODIGO%" || goto :falha
set "PUSHED=1"
echo [TIME] codigo aberto - pushd     %TIME%

rem A chave de sessao fica no disco LOCAL, nunca no share: o app roda com o
rem DebugConfig, que sem SECRET_KEY sorteia uma a cada restart e desloga todo
rem mundo.
set "SECRET_KEY_FILE=%APP_STATE_DIR%\secret_key.txt"
if not exist "%SECRET_KEY_FILE%" "%PY%" -c "import secrets; print(secrets.token_hex(32))" > "%SECRET_KEY_FILE%"
set /p "SECRET_KEY=" < "%SECRET_KEY_FILE%"

rem As dependencias so se instalam quando o requirements.txt da versao muda.
rem O retrato fica DENTRO da pasta do Python: Python reinstalado e Python sem
rem pacote, e o retrato tem de sumir junto -- num lugar comum ele diria que
rem esta tudo instalado num Python vazio.
set "REQUIREMENTS_FILE=%CODIGO%\requirements.txt"
for %%P in ("%PY%") do set "PY_HOME=%%~dpP"
set "REQUIREMENTS_SNAPSHOT=%PY_HOME%otc-requirements-%VERSION_PATH%.snapshot"
if /i "%~1"=="--reinstall" goto :instala_deps
if not exist "%REQUIREMENTS_SNAPSHOT%" goto :instala_deps
fc /b "%REQUIREMENTS_FILE%" "%REQUIREMENTS_SNAPSHOT%" >nul 2>&1 || goto :instala_deps
echo Dependencias em dia - instalacao pulada. Use --reinstall para forcar.
goto :deps_ok

:instala_deps
echo Instalando as dependencias do Python - na primeira vez leva alguns minutos...
set "ERRO=Nao consegui instalar as dependencias do Python - veja a mensagem do pip acima."
"%PY%" -m pip install --prefer-binary -r "%REQUIREMENTS_FILE%" || goto :falha
set "ERRO=Nao consegui instalar o pacote awmpy do Artifactory."
"%PY%" -m pip install --prefer-binary --index-url %ARTIFACTORY_PYPI% "awmpythoninnovation-awmpy[kerberos]" || goto :falha
copy /y "%REQUIREMENTS_FILE%" "%REQUIREMENTS_SNAPSHOT%" >nul

:deps_ok
echo [TIME] dependencias conferidas   %TIME%

rem ---------------------------------------------------------------------------
rem  Bytecode .pyc em disco LOCAL, nunca no share (HANDOFF 322).  O Python
rem  espelha a arvore do fonte dentro do prefixo DESCARTANDO a letra da
rem  unidade, entao o pushd acima pode mapear o share em qualquer letra livre;
rem  como a raiz mapeada JA E a pasta da versao, o %%VERSION_PATH%% vai no
rem  prefixo para duas versoes nao cairem no mesmo lugar.  %%LOCALAPPDATA%% e
rem  nao %%TEMP%%: a Limpeza de Disco apaga o TEMP, e a subida seguinte
rem  recompilaria tudo.  E nunca PYTHONDONTWRITEBYTECODE: ele recompila a cada
rem  subida.  Com o espelho local o prefixo e outro, pycache-teste: o fonte
rem  roda de outro caminho, e assim da para apagar um cache sem tocar no outro.
rem ---------------------------------------------------------------------------
if not defined PYTHONPYCACHEPREFIX set "PYTHONPYCACHEPREFIX=%PYCACHE_DIR%"
echo [INFO] Bytecode .pyc em: %PYTHONPYCACHEPREFIX%

rem O navegador abre quando o servidor RESPONDE, nao agora: a subida leva
rem minutos.  Qualquer resposta HTTP serve, ate erro; so conexao recusada ou
rem sem resposta e "ainda nao".  Janela propria e escondida: com /b ela
rem dividiria este console, e o -WindowStyle Hidden esconderia o servidor.
start "" /min powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "$u = 'http://127.0.0.1:8051/login'; for ($i = 0; $i -lt 900; $i++) { try { Invoke-WebRequest -Uri $u -UseBasicParsing -TimeoutSec 5 | Out-Null; $ok = $true } catch { $ok = $null -ne $_.Exception.Response }; if ($ok) { Start-Process 'http://localhost:8051'; break }; Start-Sleep -Seconds 2 }"

echo [TIME] entregando ao Python      %TIME%
echo.
echo Iniciando o OTC Tracker na porta 8051. O navegador abre sozinho quando ele estiver pronto.
echo DEIXE ESTA JANELA ABERTA: ela e o servidor. Para parar, feche-a ou aperte Ctrl+C.
echo.

rem threads=16, nao 8 (CLAUDE.md 2: escale com THREADS, nunca com processos --
rem o singleton do banco, o _cache_lock e os schedulers so valem dentro de UM
rem processo).  Com os dados no share a thread fica parada esperando rede na
rem maior parte do request.
"%PY%" -c "from waitress import serve; from run import app; serve(app, host='0.0.0.0', port=8051, threads=16)"
set "EXIT_CODE=%ERRORLEVEL%"
popd

echo.
echo O OTC Tracker parou - codigo %EXIT_CODE%.
pause
exit /b %EXIT_CODE%


rem ===========================================================================
rem  Sub-rotinas.  Voltam por `goto :eof` e quem chama confere o %%PY%%: o
rem  motivo da falha fica no %%ERRO%%, que a :falha mostra.
rem ===========================================================================

:cria_atalho
rem O alvo e o cmd.exe com o LANCADOR de argumento, entre aspas duplas
rem dobradas: o caminho tem espaco, e o cmd /c tira o par de fora.  As aspas
rem saem como [char]34 porque uma aspa dentro do -Command fecharia a string
rem do cmd.  O diretorio atual e o SystemRoot, que existe em toda maquina --
rem o atalho do share serve a todas.  So o do Desktop decide o retorno: o do
rem share depende de permissao de escrita na pasta, e a primeira maquina que
rem puder o cria para as outras.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$q = [char]34; function Atalho($lnk, $icone) { $s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk); $s.TargetPath = $env:ComSpec; $s.Arguments = '/c ' + $q + $q + $env:OTC_LAUNCHER + $q + $q; $s.WorkingDirectory = $env:SystemRoot; $s.IconLocation = $icone; $s.Description = $env:OTC_NOME; $s.Save(); Write-Host ('[INFO] Atalho criado: ' + $lnk) }; $ok = $true; try { Atalho (Join-Path ([Environment]::GetFolderPath('Desktop')) ($env:OTC_NOME + '.lnk')) $env:ICON } catch { $ok = $false; Write-Host '[AVISO] Nao consegui criar o atalho no Desktop - crie um a mao apontando para este .bat.' }; if (-not (Test-Path -LiteralPath $env:LNK_SHARE)) { try { Atalho $env:LNK_SHARE $env:ICON_SHARE } catch { Write-Host '[AVISO] Nao consegui criar o atalho na pasta do share.' } }; if (-not $ok) { exit 1 }" && type nul > "%APP_STATE_DIR%\atalho %OTC_NOME%.ok"
goto :eof

:espelha
rem ---------------------------------------------------------------------------
rem  O ESPELHO LOCAL DO CODIGO (HANDOFF 524).  Com o codigo no share, cada um
rem  dos ~313 modulos paga no import uma listagem de diretorio e um stat pelo
rem  SMB, em TODA subida, tenha havido deploy ou nao; a copia sequencial em
rem  bloco e o que o SMB faz bem.  Na instancia: 11m49s viraram 63s.
rem
rem  SO O CODIGO se move: DATA_DIR, DATABASE_DIR e SHARED_DRIVE_ROOT sao UNC
rem  absolutos no apps/config.py, e os bancos continuam os mesmos para a mesa.
rem
rem  /MIR copia so o que mudou e preserva os timestamps, entao o .pyc de um
rem  modulo que nao mudou continua valendo.  ATENCAO: /MIR tambem APAGA no
rem  destino o que nao existe na origem -- por isso o destino e uma pasta
rem  dedicada, src-teste, e nunca deve apontar para outra coisa.
rem
rem  O codigo de saida do robocopy e um BITMASK: 0 a 7 e sucesso, 8 ou mais e
rem  falha.  `if errorlevel 1` abortaria toda copia que copiou alguma coisa.
rem ---------------------------------------------------------------------------
set "ESPELHO_OK="
set "ERRO=Nao consegui espelhar o codigo para o disco local - veja a mensagem do robocopy acima."
set "ESPELHO=%APP_STATE_DIR%\src-teste\%VERSION_PATH%"
echo Espelhando o codigo para o disco local - a primeira vez demora...
robocopy "%CODIGO%" "%ESPELHO%" /MIR /XD __pycache__ .git /XF *.pyc /NFL /NDL /NJH /NJS /NP /R:2 /W:5
if errorlevel 8 goto :eof
set "CODIGO=%ESPELHO%"
set "PYCACHE_DIR=%APP_STATE_DIR%\pycache-teste\%VERSION_PATH%"
set "ESPELHO_OK=1"
echo [TIME] codigo espelhado local    %TIME%
goto :eof

:acha_python
rem %1 = a versao menor (3.13, 3.12).  Primeiro o Python PROPRIO do OTC
rem Tracker, na pasta python313/python312; senao um ja instalado para ESTE
rem usuario, pelo registro; senao o do PATH (o DevShell).  O de todos os
rem usuarios so entra pelo PATH, por ultimo: em Program Files o pip nao
rem escreve, e cai sozinho na pasta do usuario.  Achou, deixa o %%PY%%; senao,
rem o deixa como estava, vazio.
set "PY_MINOR=%~1"
set "PY_TAG=%PY_MINOR:.=%"
if exist "%APP_STATE_DIR%\python%PY_TAG%\python.exe" set "PY=%APP_STATE_DIR%\python%PY_TAG%\python.exe"
if defined PY goto :eof
set "PY_REG="
for /f "tokens=1,2,*" %%A in ('reg query "HKCU\Software\Python\PythonCore\%PY_MINOR%\InstallPath" /v ExecutablePath 2^>nul') do if /i "%%A"=="ExecutablePath" set "PY_REG=%%C"
if defined PY_REG if exist "%PY_REG%" set "PY=%PY_REG%"
if defined PY goto :eof
rem Por ultimo o python do PATH -- o do DevShell, que nao se registra no HKCU.
rem So vale o da versao pedida; o "python" da Microsoft Store (WindowsApps) e
rem um atalho que abre a loja, nao um Python, e fica de fora.
for /f "delims=" %%P in ('where python 2^>nul') do if not defined PY call :testa_python "%%P"
goto :eof

:testa_python
rem %1 = um python.exe candidato do PATH; vira o %%PY%% se for da %%PY_MINOR%%.
echo "%~1" | findstr /l /i /c:"WindowsApps" >nul && goto :eof
"%~1" -c "import sys; sys.exit(not sys.version.startswith('%PY_MINOR%.'))" >nul 2>&1 && set "PY=%~1"
goto :eof

:instala_python
rem %1 = a versao exata (3.13.14), %2 = a menor (3.13).  Instala na pasta
rem PROPRIA e procura de novo, pela pasta e pelo registro: o instalador do
rem python.org que ATUALIZA um Python da mesma versao menor ja instalado
rem ignora a pasta pedida.  Falhou, diz o motivo num AVISO e volta sem o
rem %%PY%% -- quem chama tenta a versao seguinte.
set "PY_FULL=%~1"
set "PY_MINOR=%~2"
set "PY_TAG=%PY_MINOR:.=%"
set "PY_DIR=%APP_STATE_DIR%\python%PY_TAG%"
set "PY_INSTALLER=python-%PY_FULL%-amd64.exe"
set "PY_URL=%OTC_PYTHON_FTP%/%PY_FULL%/%PY_INSTALLER%"
echo.
echo Primeira vez nesta maquina: instalando o Python %PY_FULL% do OTC Tracker
echo em %PY_DIR% - so para este usuario, sem admin.
set "INSTALLER=%SHARE_ROOT%\installers\%PY_INSTALLER%"
if exist "%INSTALLER%" goto :confere_instalador
set "INSTALLER=%TEMP%\%PY_INSTALLER%"
echo Baixando %PY_URL%
rem Pelo proxy do sistema e com as credenciais do Windows: primeiro o
rem Invoke-WebRequest, e se ele falhar o BITS, que autentica sozinho no proxy.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference = 'SilentlyContinue'; try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}; try { [Net.WebRequest]::DefaultWebProxy.Credentials = [Net.CredentialCache]::DefaultNetworkCredentials } catch {}; try { Invoke-WebRequest -Uri $env:PY_URL -OutFile $env:INSTALLER -UseBasicParsing; exit 0 } catch { Write-Host $_.Exception.Message }; try { Start-BitsTransfer -Source $env:PY_URL -Destination $env:INSTALLER; exit 0 } catch { Write-Host $_.Exception.Message }; exit 1" || goto :sem_download

:confere_instalador
powershell -NoProfile -ExecutionPolicy Bypass -Command "if ((Get-AuthenticodeSignature -LiteralPath $env:INSTALLER).Status -ne 'Valid') { exit 1 }" || goto :instalador_invalido
echo Instalando - leva um ou dois minutos...
start "" /wait "%INSTALLER%" /quiet InstallAllUsers=0 TargetDir="%PY_DIR%" PrependPath=0 AssociateFiles=0 Shortcuts=0 Include_launcher=0 InstallLauncherAllUsers=0 Include_doc=0 Include_test=0 Include_tcltk=0 Include_pip=1
call :acha_python %PY_MINOR%
if not defined PY echo [AVISO] O instalador do Python %PY_FULL% terminou sem deixar o python.exe. Se o Windows disse "blocked by group policy", a politica desta maquina barra o instalador - o caminho e o Python do DevShell, no [ERRO] abaixo. Senao, o log fica em %TEMP%, nos arquivos Python*.log.
goto :eof

:sem_download
echo [AVISO] Nao consegui baixar o Python %PY_FULL% - coloque o %PY_INSTALLER% na pasta installers ao lado deste .bat, no share.
goto :eof

:instalador_invalido
echo [AVISO] O %INSTALLER% nao e um instalador assinado do Python - apague-o e rode de novo.
goto :eof

:falha
echo.
echo [ERRO] %ERRO%
echo.
if defined PUSHED popd
pause
exit /b 1
