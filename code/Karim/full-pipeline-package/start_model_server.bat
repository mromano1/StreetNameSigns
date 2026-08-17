@echo off
cd /d "%~dp0scripts"
..\venv\Scripts\python.exe serve_physical_model.py
pause
