@echo off
REM ===========================================================================
REM  IA Locale - Verification Complete V2 (double-clic)
REM  Diagnostic -> Test reel -> Re-diagnostic
REM ===========================================================================
title IA Locale - Verification V2
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0TEST.ps1" %*
pause
