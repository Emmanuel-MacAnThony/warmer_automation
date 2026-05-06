@echo off
cd /d "%~dp0.."
set PYTHONPATH=%CD%
venv_312\Scripts\python.exe backend\core\server.py
