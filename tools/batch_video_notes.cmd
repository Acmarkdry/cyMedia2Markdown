@echo off
set "ROOT=%~dp0.."
if not "%M2M_PYTHON%"=="" (
  set "PY=%M2M_PYTHON%"
  set "PYARGS="
) else if exist "%ROOT%\.venv-gpu\Scripts\python.exe" (
  set "PY=%ROOT%\.venv-gpu\Scripts\python.exe"
  set "PYARGS="
) else if exist "%ROOT%\.venv-cpu\Scripts\python.exe" (
  set "PY=%ROOT%\.venv-cpu\Scripts\python.exe"
  set "PYARGS="
) else (
  set "PY=py"
  set "PYARGS=-3.12"
)
"%PY%" %PYARGS% "%ROOT%\tools\batch_video_notes.py" %*
exit /b %ERRORLEVEL%
