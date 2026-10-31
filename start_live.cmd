@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Virtual environment missing. Run from your existing Proxmox-Monitor project.
 pause
 exit /b 1
)
.venv\Scripts\python.exe logger.py
pause
