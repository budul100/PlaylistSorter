@echo off
REM --- Interactive Playlist Sorting Batch Script ---
REM Usage: double-click and enter the path, or drag & drop a playlist file onto this file.

REM --- Configuration ---
REM The Python script is expected next to this batch file.
SET "SORT_SCRIPT_PATH=%~dp0playlist-sorter.py"
SET "OUTPUT_SUFFIX=_sorted"
REM What to do with tracks that cannot be optimized (missing tags, unreadable files):
REM   separate = write them to a second playlist (<name>_unsorted.m3u)
REM   append   = append them to the end of the sorted playlist
REM   omit     = leave them out
SET "UNSORTED_MODE=separate"
REM Optional extra arguments, e.g.: --first "opener.mp3" --last "closer.mp3" --trend up
SET "EXTRA_ARGS="
REM ---------------------

echo.
echo ------------------------
echo Harmonic Playlist Sorter
echo ------------------------
echo.

REM Check if the Python script exists
if not exist "%SORT_SCRIPT_PATH%" (
    echo ERROR: Python script not found at "%SORT_SCRIPT_PATH%".
    echo Please ensure playlist-sorter.py is next to this file or update the SORT_SCRIPT_PATH variable.
    pause
    goto :EOF
)

REM Use 'python', fall back to the 'py' launcher
SET "PYTHON_CMD=python"
where python >nul 2>nul
if errorlevel 1 SET "PYTHON_CMD=py -3"

REM --- 1. Get Input Path ---
REM A file dropped onto this batch file is passed as the first argument.
set "INPUT_PATH=%~1"
if defined INPUT_PATH goto CheckInput

:AskInput
set "INPUT_PATH="
set /p INPUT_PATH="Enter the path to the INPUT M3U file: "

REM Check if the path is empty (uses 'if not defined' to avoid syntax errors)
if not defined INPUT_PATH (
    echo ERROR: Input path cannot be empty.
    goto AskInput
)

:CheckInput
REM Remove ALL double quotes from the variable to normalize it.
REM This handles both quoted input (Drag&Drop) and unquoted input safely.
set "INPUT_PATH=%INPUT_PATH:"=%"

REM Check if the file exists (Now we add quotes manually for safety)
if not exist "%INPUT_PATH%" (
    echo ERROR: File not found at "%INPUT_PATH%". Please check the path and try again.
    goto AskInput
)

REM --- 2. Generate Output Path ---

REM Extract file extension (e.g., .m3u)
for %%x in ("%INPUT_PATH%") do set "EXTENSION=%%~xx"
REM Extract path without extension
for %%x in ("%INPUT_PATH%") do set "BASE_PATH=%%~dpx%%~nx"

REM Combine base path, suffix, and extension
SET "OUTPUT_PATH=%BASE_PATH%%OUTPUT_SUFFIX%%EXTENSION%"

echo.
echo Input Playlist: %INPUT_PATH%
echo Automatically generated Output Playlist: %OUTPUT_PATH%
echo Unsorted tracks: %UNSORTED_MODE%
echo --------------------------------------------------

REM --- 3. Execute Python Script ---
%PYTHON_CMD% "%SORT_SCRIPT_PATH%" "%INPUT_PATH%" "%OUTPUT_PATH%" --unsorted %UNSORTED_MODE% %EXTRA_ARGS%

REM --- 4. Check Result ---
if %errorlevel% neq 0 (
    echo.
    echo --------------------------------------------------------------------------------
    echo EXECUTION FAILED! The Python script returned an error.
    echo Check the messages above for details.
    echo --------------------------------------------------------------------------------
) else (
    echo.
    echo Sorting completed successfully. Check the output file: %OUTPUT_PATH%
)

echo.
pause
