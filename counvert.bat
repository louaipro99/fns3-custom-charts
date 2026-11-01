@echo off
if "%~1"=="" (
    echo Drag and drop an .osz or .zip file onto this script.
    pause
    exit /b
)

if /i "%~x1"==".osz" (
    python "%~dp0module\osz_to_fns3.py" "%~1"
    pause
    exit /b
)

if /i "%~x1"==".zip" (
    python "%~dp0module\install_chart.py" "%~1"
    pause
    exit /b
)

echo Error: Drop an .osz to convert or a .zip to install.
pause
