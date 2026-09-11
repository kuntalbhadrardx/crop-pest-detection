@echo off
REM One-click start for the Crop Pest & Disease Detector.
REM Runs the API + Streamlit, waits for both, then opens the browser.
cd /d "%~dp0"
echo Starting Crop Pest & Disease Detector...
wsl -d Ubuntu-26.04 -- bash ./run_all.sh
echo.
echo Opening browser (UI)...
start "" http://127.0.0.1:8501
pause
