@echo off
rem Build OY Player for people: dist\OYPlayer\ (the program, PyInstaller onedir) and
rem dist\OYPlayer-<version>-setup.exe (Inno Setup, per-user install, no administrator).
rem     tools\build.cmd
rem Needs: PyInstaller in .venv (requirements-build.txt), Inno Setup 6.
rem Logs: build\pyinstaller.log, build\iscc.log
setlocal
chcp 65001 >nul
set ROOT=%~dp0..
cd /d "%ROOT%"
if not exist build mkdir build
"%ROOT%\.venv\Scripts\python.exe" -c "import sys; sys.path.insert(0, 'src'); import oyplayer; print(oyplayer.__version__)" > build\version.txt
set /p VER=<build\version.txt
echo OY Player %VER%
rem What PyInstaller collects must not depend on what is on this machine's PATH: Git for
rem Windows' OpenSSL once came in that way. Windows and the venv only, for the build.
set "PATH=%SystemRoot%\System32;%SystemRoot%;%ROOT%\.venv\Scripts"
"%ROOT%\.venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --distpath "%ROOT%\dist" --workpath "%ROOT%\build\pyinstaller" "%ROOT%\tools\oyplayer.spec" > "%ROOT%\build\pyinstaller.log" 2>&1
if errorlevel 1 (echo PyInstaller failed, see build\pyinstaller.log & exit /b 1)
rem the licences go beside the program: OY Player's GPL, what each bundled component is under,
rem and the FFmpeg build's own licence (the GPL asks for them with every copy)
set FFDIR=%OY_FFMPEG_DIR%
if "%FFDIR%"=="" set FFDIR=C:\ProgramData\chocolatey\lib\ffmpeg\tools\ffmpeg\bin
copy /y "%ROOT%\LICENSE" "%ROOT%\dist\OYPlayer\LICENSE.txt" >nul || (echo LICENSE missing & exit /b 1)
copy /y "%ROOT%\THIRD-PARTY-NOTICES.md" "%ROOT%\dist\OYPlayer\THIRD-PARTY-NOTICES.md" >nul || (echo notices missing & exit /b 1)
if not exist "%ROOT%\dist\OYPlayer\licenses" mkdir "%ROOT%\dist\OYPlayer\licenses"
copy /y "%FFDIR%\..\LICENSE" "%ROOT%\dist\OYPlayer\licenses\FFmpeg-LICENSE.txt" >nul || (echo FFmpeg LICENSE missing & exit /b 1)
echo program: dist\OYPlayer\OYPlayer.exe
rem Inno Setup per user here, for all users on the build server
set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
"%ISCC%" /Q /DAppVersion=%VER% "%ROOT%\tools\installer.iss" > "%ROOT%\build\iscc.log" 2>&1
if errorlevel 1 (echo Inno Setup failed, see build\iscc.log & exit /b 1)
echo installer: dist\OYPlayer-%VER%-setup.exe
exit /b 0
