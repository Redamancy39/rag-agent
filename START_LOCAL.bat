@echo off
setlocal
chcp 65001 >nul
title RAG Agent - Local Launcher
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-local.ps1" %*
set "LAUNCH_RESULT=%ERRORLEVEL%"
if not "%LAUNCH_RESULT%"=="0" echo [ERROR] Launch failed. See the message above.
if not "%RAG_LAUNCHER_NO_PAUSE%"=="1" pause
exit /b %LAUNCH_RESULT%
