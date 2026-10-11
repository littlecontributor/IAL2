@echo off
setlocal
REM ===========================================================================
REM  IA Locale - Installation Cle en Main V2 (double-clic)
REM  Diagnostic -> Install -> Re-diagnostic
REM ===========================================================================
title IA Locale - Installation V2 Cle en Main
cd /d "%~dp0"
set "INSTALL_SCRIPT=%~dp0INSTALL.ps1"
echo ======================================================================
echo   IA LOCALE - INSTALLATION CLE EN MAIN V2
echo   Diagnostic -> Telechargement composants -> Re-diagnostic
echo ======================================================================
echo.
echo Strategie PowerShell actuelle (diagnostic en lecture seule) :
powershell.exe -NoProfile -Command "Get-ExecutionPolicy -List | Format-Table -AutoSize"
echo.
echo Lancement de l'installation dans un processus PowerShell temporaire...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%INSTALL_SCRIPT%" %*
set "INSTALL_EXIT=%ERRORLEVEL%"
if not "%INSTALL_EXIT%"=="0" (
    echo.
    echo Le lanceur PowerShell a echoue (code %INSTALL_EXIT%).
    echo Consultez la strategie affichee plus haut.
    echo Si MachinePolicy ou UserPolicy est defini, demandez un installateur approuve a l'administrateur.
    echo Ne modifiez pas la strategie globale de Windows.
    echo Si ces deux champs sont Undefined et que vous faites confiance au ZIP, dans ce dossier :
    echo   Unblock-File .\INSTALL.ps1
    echo   .\INSTALL.bat -Recreate
)
pause
exit /b %INSTALL_EXIT%
