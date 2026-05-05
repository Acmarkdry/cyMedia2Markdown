@echo off
set "ROOT=%~dp0.."
set "PY=%ROOT%\backend\.venv\Scripts\python.exe"
"%PY%" "%ROOT%\tools\launch_parallel_regeneration.py" %*
exit /b %ERRORLEVEL%
