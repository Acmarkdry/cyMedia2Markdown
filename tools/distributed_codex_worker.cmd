@echo off
call "%~dp0distributed_video_notes.cmd" codex-worker %*
exit /b %ERRORLEVEL%
