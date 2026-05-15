@echo off
set "ROOT=%~dp0.."
if not "%M2M_PYTHON%"=="" (
  set "PY=%M2M_PYTHON%"
  set "PYARGS="
) else (
  set "PY=py"
  set "PYARGS=-3.12"
)
"%PY%" %PYARGS% "%ROOT%\tools\article_washing.py" %*
exit /b %ERRORLEVEL%
