@echo off
set "ROOT=%~dp0.."
set "PY=%ROOT%\backend\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" "%ROOT%\tools\distributed_video_notes.py" %*
exit /b %ERRORLEVEL%
