@echo off

echo.

set "scriptname=Playlist-Sorter.py"

for %%i in ("%scriptname%") do set "scriptbase=%%~ni"

pyinstaller --onefile --distpath . "%scriptname%"

if exist "%scriptbase%.spec" del "%scriptbase%.spec"

rmdir /S /Q build

echo.
echo Build completed.

pause