@echo off
echo ========================================
echo   Exhibition Sales CRM - 2Click Next
echo ========================================
echo.
echo Starting app at http://localhost:3000
echo Press Ctrl+C to stop.
echo.
docker compose -f "%~dp0compose.yml" --project-directory "%~dp0" up --build
