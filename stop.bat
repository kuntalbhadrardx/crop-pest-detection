@echo off
REM One-click stop for the Crop Pest & Disease Detector.
cd /d "%~dp0"
echo Stopping Crop Pest & Disease Detector...
wsl -d Ubuntu-26.04 -- bash -c "pkill -f '[u]vicorn app.main'; pkill -f '[s]treamlit run'"
echo Done.
pause
