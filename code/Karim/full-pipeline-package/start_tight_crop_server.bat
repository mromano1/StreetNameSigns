@echo off
rem Local server the annotation tool calls every time you draw a box: turns
rem the box into a tight, high-resolution Cyclomedia re-render of just that
rem sign (real added detail over the wide panorama capture), and also feeds
rem the physical model's live damage-guess suggestion. Needs this running
rem alongside start_annotation_server.bat while annotating.
cd /d "%~dp0scripts"
..\venv\Scripts\python.exe serve_tight_crop.py
pause
