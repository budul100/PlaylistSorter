@echo off

set exePath=Playlist-Sorter.exe

title Sort m3u playlists

set /p filePath=Enter path of the playlist: 

if not exist "%filePath%" (
    echo File "%filePath%" does not exist. Please check the path.
    pause
    exit /b
)

echo.
"%exePath%" "%filePath%"
echo.

pause
