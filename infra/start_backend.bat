@echo off
cd /d "%~dp0.."
echo ========================================
echo LinkedIn Enrichment API - Starting...
echo ========================================
echo.

python -m backend.core.server

pause
