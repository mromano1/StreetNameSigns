@echo off
rem Serves the annotation tool with ML Project as the HTTP root, since
rem annotate.js fetches /data/cyclomedia_panoramas/fetch_manifest.json
rem as an absolute path -- opening index.html directly (file://) fails
rem with "NetworkError when attempting to fetch resource".
cd /d "%~dp0.."
start "" "http://localhost:8000/annotation_tool/index.html"
venv\Scripts\python.exe -m http.server 8000
pause
