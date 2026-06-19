# Installation Guide

## Prerequisites

- Python 3.8 or higher
- 4GB RAM minimum
- 500MB disk space

## Windows Installation

1. Install Python from [python.org](https://python.org) (check "Add to PATH")

2. Open Command Prompt in the project folder:

```cmd
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Or double-click `run.bat`.

## Linux (Ubuntu) Installation

1. Install system dependencies:

```bash
sudo apt update
sudo apt install python3 python3-tk python3-pip python3-venv -y
```

2. Create virtual environment (required due to PEP 668):

```bash
cd attendance_system
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

Or run `./run.sh`.

## Linux — One-Click App (No venv Each Time)

**Important:** Build on Linux (Ubuntu). You cannot create a Linux executable from Windows.

### Quick build (recommended)

```bash
cd attendance_system
chmod +x build_linux.sh
./build_linux.sh
```

This will:
1. Install dependencies in a local `venv` (build only)
2. Package the app with PyInstaller
3. Install to `~/.local/share/AttendanceSystem/`
4. Add **Attendance System** to your application menu (and Desktop if present)

After that, open it like any other app — no `source venv` needed.

### Your data

When installed as an app, data is stored in:

```
~/.config/AttendanceSystem/
├── attendance.db
├── config.json
├── imports/
├── exports/
├── backups/
└── logs/
```

### Manual PyInstaller build

```bash
source venv/bin/activate
pip install pyinstaller
pyinstaller --windowed --onedir --name AttendanceSystem \
  --hidden-import=matplotlib.backends.backend_tkagg \
  --collect-all matplotlib \
  main.py
```

Run: `./dist/AttendanceSystem/AttendanceSystem`

Use `--onedir` (folder) instead of `--onefile` for faster startup and fewer Tkinter issues on Linux.

## Windows Standalone Build

```cmd
pip install pyinstaller
pyinstaller --windowed --onedir --name AttendanceSystem main.py
```

Run: `dist\AttendanceSystem\AttendanceSystem.exe`

## Troubleshooting

### Tkinter not found (Linux)
```bash
sudo apt install python3-tk
```

### Permission denied on run.sh
```bash
chmod +x run.sh
```

### Import errors
Ensure the virtual environment is activated and all dependencies are installed:
```bash
pip install -r requirements.txt
```

## Configuration

Settings are stored in:
- **Windows**: `%LOCALAPPDATA%\AttendanceSystem\config.json`
- **Linux**: `~/.config/AttendanceSystem/config.json`

Database location defaults to `attendance_system/attendance.db` and can be changed in Settings.
