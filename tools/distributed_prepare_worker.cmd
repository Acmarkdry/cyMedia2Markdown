@echo off
call "%~dp0distributed_video_notes.cmd" prepare-worker %*
exit /b %ERRORLEVEL%
