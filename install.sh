#!/bin/bash

# Security Camera Dashboard - Install Script
# Run this on the remote server after uploading

set -e

echo "=== Security Camera Dashboard Installer ==="

# Get the directory where the script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/home/pyr/sec-camera-dashboard"

# Check if we need to move files
if [ "$SCRIPT_DIR" != "$INSTALL_DIR" ]; then
    echo "Moving files to $INSTALL_DIR..."
    mkdir -p "$INSTALL_DIR"
    cp -r "$SCRIPT_DIR"/* "$INSTALL_DIR"/
    cd "$INSTALL_DIR"
else
    cd "$INSTALL_DIR"
fi

echo "Working directory: $(pwd)"

# Install system dependencies
echo "Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv ffmpeg

# Create virtual environment
echo "Creating Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install fastapi uvicorn python-telegram-bot opencv-python-headless pillow pydantic pydantic-settings aiosqlite numpy

# Create data directories
echo "Creating data directories..."
mkdir -p data/recordings data/hls data/detections data/thumbnails data/models

# Copy service file
echo "Installing systemd service..."
sudo cp sec-camera.service /etc/systemd/system/
sudo systemctl daemon-reload

# Enable and start service
echo "Enabling and starting service..."
sudo systemctl enable sec-camera
sudo systemctl start sec-camera

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Commands:"
echo "  sudo systemctl status sec-camera   # Check status"
echo "  sudo systemctl restart sec-camera  # Restart"
echo "  sudo systemctl stop sec-camera     # Stop"
echo "  sudo journalctl -u sec-camera -f   # View logs"
echo ""
echo "Dashboard URL: http://$(hostname -I | awk '{print $1}'):5001"
echo ""
