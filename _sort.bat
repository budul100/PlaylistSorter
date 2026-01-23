@echo off
REM --- Interactive Playlist Sorting Batch Script ---

REM --- Configuration ---
SET "SORT_SCRIPT_PATH=.\playlist-sorter.py"
SET "OUTPUT_SUFFIX=_sorted"
REM ---------------------

echo.
echo ------------------------
echo Harmonic Playlist Sorter
echo ------------------------
echo.

REM Check if the Python script exists
if not exist "%SORT_SCRIPT_PATH%" (
    echo ERROR: Python script not found at "%SORT_SCRIPT_PATH%".
    echo Please ensure the script is in the correct location or update the SORT_SCRIPT_PATH variable.
    pause
    goto :EOF
)

REM --- 1. Get Input Path ---
:AskInput
set "INPUT_PATH="
set /p INPUT_PATH="Enter the path to the INPUT M3U file: "

REM Check if the path is empty (uses 'if not defined' to avoid syntax errors)
if not defined INPUT_PATH (
    echo ERROR: Input path cannot be empty.
    goto AskInput
)

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
echo --------------------------------------------------

REM --- 3. Execute Python Script ---
REM Call the Python script using the defined constant.
python "%SORT_SCRIPT_PATH%" "%INPUT_PATH%" "%OUTPUT_PATH%"

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
