#!/bin/bash

echo ">>> Starting Advanced Downloader Bot Installation..."

# Update package lists
echo ">>> [1/5] Updating system packages..."
sudo apt-get update -y

# Install Python, pip, and venv
echo ">>> [2/5] Installing Python essentials..."
sudo apt-get install -y python3 python3-pip python3-venv

# Install FFmpeg for video processing
echo ">>> [3/5] Installing FFmpeg..."
sudo apt-get install -y ffmpeg

# Create a virtual environment
echo ">>> [4/5] Creating Python virtual environment..."
python3 -m venv venv

# Activate the virtual environment and install dependencies
echo ">>> [5/5] Installing required Python packages..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "✅ Installation Complete!"
echo "--------------------------------------------------"
echo "To run the bot, first upload your project to the server, then:"
echo "1. Activate environment: source venv/bin/activate"
echo "2. Run main bot:       python main_bot.py"
echo "3. Run worker client:  python advanced_worker.py (in a separate terminal)"
echo "--------------------------------------------------"
