@echo off
rem Interactive terminal wizard for the Community-Board-to-trained-model
rem pipeline: select a board, pull SIMS signs + Cyclomedia panoramas, then
rem choose manual (annotate yourself) or automatic (section-missing stub
rem today) mode. See docs/superpowers/specs/2026-08-13-pipeline-shell-design.md.
cd /d "%~dp0scripts"
..\venv\Scripts\python.exe pipeline_shell.py
pause
