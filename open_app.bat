@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" main.py
) else (
  if exist "%SystemRoot%\py.exe" (
    py -3 main.py
  ) else (
    python main.py
  )
)
