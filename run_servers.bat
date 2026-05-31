@echo off
REM Launch Site B and Site A servers for the DGC project.
REM Run this file from the project root.

SET ROOT_DIR=%~dp0
SET VENV_ACTIVATE=%ROOT_DIR%venv\Scripts\activate.bat

if exist "%VENV_ACTIVATE%" (
  start "Site B" cmd /k "cd /d "%ROOT_DIR%" && call "%VENV_ACTIVATE%" && python -m uvicorn api.server:app --port 8000"
  start "Site A" cmd /k "cd /d "%ROOT_DIR%" && call "%VENV_ACTIVATE%" && python -m uvicorn api.site_a_server:app --port 8001"
) else (
  echo WARNING: Virtual environment not found at "%VENV_ACTIVATE%".
  echo Falling back to system python.
  start "Site B" cmd /k "cd /d "%ROOT_DIR%" && python -m uvicorn api.server:app --port 8000"
  start "Site A" cmd /k "cd /d "%ROOT_DIR%" && python -m uvicorn api.site_a_server:app --port 8001"
)

echo Started Site B on port 8000 and Site A on port 8001.
pause
