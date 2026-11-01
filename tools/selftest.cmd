@echo off
rem Self-test on the real window (display 3, silent, input-transparent).
rem Always the same command, so one permission rule covers every run:
rem     tools\selftest.cmd
rem Results: tests\out\  (out.txt = full output, *.png = window captures, home\ = app state)
rem Exit code 0 = all checks passed.
rem One run of the built program instead (after tools\build.cmd): create the empty file
rem tests\next-run-exe. The run uses it up, so the next run tests the development code again.
rem A quick run (about a minute) and only the blocks of the change: tests\next-run-focus with
rem block names (base editor draw ideas m8 fb1 fb2 fb3 st1 st3 st4 tails fb4 upd skins), used up
rem the same way; empty, the quick part alone. Before a release, the full run.
rem The master screenshots instead (src\oyplayer\showcase.py): create the empty file
rem tests\next-run-showcase, used up the same way; the captures land in tests\out\showcase.
setlocal
chcp 65001 >nul
set ROOT=%~dp0..
set OUT=%ROOT%\tests\out
set "TARGET=dev"
if exist "%ROOT%\tests\next-run-exe" (
    set "TARGET=exe"
    del "%ROOT%\tests\next-run-exe"
)
if exist "%ROOT%\tests\next-run-showcase" (
    set "TARGET=showcase"
    del "%ROOT%\tests\next-run-showcase"
)
echo target=%TARGET%
rem A run starts from nothing: stale settings or playlist from the last run must not leak in.
if exist "%OUT%" rmdir /s /q "%OUT%"
mkdir "%OUT%"
set OY_HOME=%OUT%\home
set OY_SHOTS=%OUT%\shots
set PYTHONIOENCODING=utf-8
if "%TARGET%"=="exe" goto exe
if "%TARGET%"=="showcase" goto showcase
cd /d "%ROOT%\src"
"%ROOT%\.venv\Scripts\python.exe" -u -m oyplayer --selftest "%ROOT%\tests\media\test720.mp4" "%OUT%" > "%OUT%\out.txt" 2>&1
set CODE=%ERRORLEVEL%
findstr /c:"SELFCHECK FAIL" /c:"SELFCHECK SKIP" /c:"SELFCHECK RESULT" "%OUT%\out.txt"
echo exit=%CODE%
exit /b %CODE%

:exe
rem the built program has no console: its checks are read from its log
start "" /wait "%ROOT%\dist\OYPlayer\OYPlayer.exe" --selftest "%ROOT%\tests\media\test720.mp4" "%OUT%"
set CODE=%ERRORLEVEL%
findstr /c:"SELFCHECK" "%OUT%\home\oyplayer.log" > "%OUT%\out.txt"
findstr /c:"SELFCHECK FAIL" /c:"SELFCHECK SKIP" "%OUT%\out.txt"
rem Windows' own find: started from Git Bash, a plain "find" is GNU find, which walks C:\
for /f %%n in ('findstr /c:"SELFCHECK PASS" "%OUT%\out.txt" ^| "%SystemRoot%\System32\find.exe" /c /v ""') do echo passed=%%n
echo exit=%CODE%
exit /b %CODE%

:showcase
cd /d "%ROOT%\src"
"%ROOT%\.venv\Scripts\python.exe" -u -m oyplayer --showcase "%ROOT%\tests\media\showcase" "%OUT%" > "%OUT%\out.txt" 2>&1
set CODE=%ERRORLEVEL%
findstr /c:"SHOWCASE" /c:"SELFCHECK FAIL" "%OUT%\out.txt"
echo exit=%CODE%
exit /b %CODE%
