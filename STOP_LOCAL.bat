@echo off
setlocal
chcp 65001 >nul
title RAG Agent - Stop Local Services
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-local.ps1" -Action stop
set "LAUNCH_RESULT=%ERRORLEVEL%"
if not "%RAG_LAUNCHER_NO_PAUSE%"=="1" pause
exit /b %LAUNCH_RESULT%
