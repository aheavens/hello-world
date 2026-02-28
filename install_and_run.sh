#!/usr/bin/env bash
# PDF Search Tool — macOS / Linux installer + launcher
# Run once with:  bash install_and_run.sh
# After that you can just run:  python3 pdf_search_tool.py

set -e

echo "============================================================"
echo "  PDF Search Tool — Setup"
echo "============================================================"
echo

# Check Python 3
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 is not installed."
    echo
    echo "macOS:  Install from https://www.python.org/downloads/"
    echo "        or run:  brew install python"
    echo "Linux:  sudo apt install python3 python3-pip   (Debian/Ubuntu)"
    echo "        sudo dnf install python3               (Fedora/RHEL)"
    exit 1
fi

echo "Python 3 found: $(python3 --version)"
echo
echo "Installing required Python packages..."
python3 -m pip install --user -r requirements.txt || {
    echo
    echo "WARNING: Some packages failed. Core functionality still works."
    echo "For OCR (scanned PDFs), also install Tesseract:"
    echo "  macOS:  brew install tesseract"
    echo "  Ubuntu: sudo apt install tesseract-ocr"
}

echo
echo "============================================================"
echo "  Starting PDF Search Tool..."
echo "============================================================"
echo

python3 pdf_search_tool.py
