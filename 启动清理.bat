@echo off
cd /d "%~dp0"
where pythonw >nul 2>nul
if %errorlevel%==0 (
  start "" pythonw cpan_gui.py
) else (
  start "" python cpan_gui.py
)
