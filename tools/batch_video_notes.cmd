@echo off
set "ROOT=%~dp0.."
set "PY=%ROOT%\backend\.venv\Scripts\python.exe"
"%PY%" "%ROOT%\tools\batch_video_notes.py" %*
exit /b %ERRORLEVEL%
