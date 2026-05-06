@echo off
REM Run server with Python 3.12 venv
set PYTHONPATH=%CD%
venv_312\Scripts\python.exe backend\core\server.py
