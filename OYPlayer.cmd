@echo off
rem Start OY Player (development build). Usage: OYPlayer.cmd [file]
cd /d "%~dp0src"
start "" "%~dp0.venv\Scripts\pythonw.exe" -m oyplayer %*
