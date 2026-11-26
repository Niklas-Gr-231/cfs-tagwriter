@echo off
rem SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
setlocal
if exist "%~dp0.venv\Scripts\python.exe" (
  "%~dp0.venv\Scripts\python.exe" "%~dp0start.py" %*
) else (
  py -3 "%~dp0start.py" %*
)
if errorlevel 1 pause
