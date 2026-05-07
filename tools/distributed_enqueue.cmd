@echo off
call "%~dp0distributed_video_notes.cmd" enqueue %*
exit /b %ERRORLEVEL%
