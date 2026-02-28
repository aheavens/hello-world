@echo off
:: PDF Search Tool — Windows installer + launcher
:: Double-click this file to install everything and start the app.

title PDF Search Tool — Setup

echo ============================================================
echo   PDF Search Tool — First-Time Setup
echo ============================================================
echo.

:: Check Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not on your PATH.
    echo.
    echo Please download Python from https://www.python.org/downloads/
    echo Make sure to tick "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

echo Python found.  Installing required packages...
echo (This may take a minute on first run.)
echo.

pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo WARNING: Some packages failed to install.
    echo The tool will still work for text-based PDFs.
    echo For OCR (scanned PDFs) you also need Tesseract:
    echo   https://github.com/UB-Mannheim/tesseract/wiki
    echo.
)

echo.
echo ============================================================
echo   Starting PDF Search Tool...
echo ============================================================
echo.

python pdf_search_tool.py

pause
