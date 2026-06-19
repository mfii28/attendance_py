#!/bin/bash
# Build standalone Attendance System for Linux (run this ON Ubuntu/Linux)
set -e

cd "$(dirname "$0")"
APP_NAME="AttendanceSystem"

echo "=== Attendance System — Linux Build ==="

# System packages (Tkinter required for GUI)
if ! python3 -c "import tkinter" 2>/dev/null; then
    echo "Installing python3-tk..."
    sudo apt update
    sudo apt install -y python3 python3-venv python3-tk python3-pip
fi

# Virtual environment for build
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate

pip install -q --upgrade pip
pip install -q -r requirements.txt
pip install -q pyinstaller

echo "Building application (this may take a few minutes)..."

pyinstaller --noconfirm --clean \
    --name "$APP_NAME" \
    --windowed \
    --onedir \
    --hidden-import=matplotlib.backends.backend_tkagg \
    --hidden-import=pandas \
    --hidden-import=openpyxl \
    --hidden-import=reportlab \
    --hidden-import=PIL \
    --hidden-import=chardet \
    --collect-all matplotlib \
    main.py

INSTALL_DIR="$HOME/.local/share/$APP_NAME"
DESKTOP_DIR="$HOME/.local/share/applications"
DESKTOP_FILE="$DESKTOP_DIR/${APP_NAME}.desktop"

echo "Installing to $INSTALL_DIR ..."
rm -rf "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
cp -r "dist/$APP_NAME/"* "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/$APP_NAME"

mkdir -p "$DESKTOP_DIR"
cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Attendance System
Comment=Employee attendance management
Exec=$INSTALL_DIR/$APP_NAME
Icon=applications-office
Terminal=false
Categories=Office;Utility;
StartupWMClass=$APP_NAME
EOF

chmod +x "$DESKTOP_FILE"

# Optional: shortcut on Desktop
if [ -d "$HOME/Desktop" ]; then
    cp "$DESKTOP_FILE" "$HOME/Desktop/${APP_NAME}.desktop"
    chmod +x "$HOME/Desktop/${APP_NAME}.desktop"
    echo "Desktop shortcut created."
fi

echo ""
echo "=== Build complete ==="
echo "Launch from app menu: 'Attendance System'"
echo "Or run: $INSTALL_DIR/$APP_NAME"
echo ""
echo "Data folder: ~/.config/AttendanceSystem/"
echo "  (database, imports, exports, settings)"
