@echo off
setlocal

rem ===========================================================================
rem  OTC Tracker NAEAST - a mesma subida do start-otc-tracker.bat, com o codigo
rem  ESPELHADO para o disco local antes de subir (HANDOFF 524 e 628).
rem
rem  Com o codigo no share, a subida levava ~12 min: cada um dos ~313 modulos
rem  paga no import uma listagem de diretorio e um stat pelo SMB, em toda
rem  subida.  Copiado para o disco local de uma vez, na instancia, 11m49s
rem  viraram 63s.  A PRIMEIRA subida por aqui e fria -- copia a arvore e
rem  compila tudo, num cache de bytecode separado, pycache-teste --; o numero
rem  que interessa e o da segunda em diante.  So o CODIGO se move: os dados e
rem  os bancos continuam no share, os mesmos da mesa.
rem
rem  Este arquivo so LIGA o espelho e da nome e atalho proprios; o resto -- o
rem  Python sem DevShell, as dependencias, o navegador, o atalho -- e o
rem  start-otc-tracker.bat, que tem de estar na MESMA pasta.  Duplo clique e
rem  pronto; na primeira vez ele poe o atalho "OTC Tracker NAEAST" no Desktop
rem  e na pasta do share.
rem ===========================================================================

if not exist "%~dp0start-otc-tracker.bat" (
    echo [ERRO] O start-otc-tracker.bat tem de estar na mesma pasta deste arquivo.
    pause
    exit /b 1
)

set "OTC_NOME=OTC Tracker NAEAST"
set "OTC_LAUNCHER=%~f0"
set "OTC_ESPELHO_LOCAL=1"
call "%~dp0start-otc-tracker.bat" %*
