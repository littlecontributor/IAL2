@echo off
REM ===========================================================================
REM  IA Locale - Demarrage V2 (double-clic)
REM ===========================================================================
title IA Locale - Demarrage V2
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0START.ps1" %*
pause
