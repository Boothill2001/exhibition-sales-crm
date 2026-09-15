@echo off
echo Resetting database (removing volumes)...
docker compose -f "%~dp0compose.yml" --project-directory "%~dp0" down --volumes --remove-orphans
echo Done. Next start will re-import data.
