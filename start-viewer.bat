@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
if errorlevel 1 goto directory_error

if not exist ".venv\Scripts\python.exe" goto environment_error
if not exist ".venv\Scripts\pythonw.exe" goto environment_error
if not exist "STDF-Viewer.py" goto source_error
if not exist "logs\" mkdir "logs"
if not exist "logs\" goto directory_error

".venv\Scripts\python.exe" -X utf8 -c "import PyQt5.QtWidgets, PyQt5.QtSql, PyQt5.QtNetwork, numpy, pydantic, pyqtgraph, tomlkit, xlsxwriter, rust_stdf_helper" >"logs\launcher-check.log" 2>&1
if errorlevel 1 goto dependency_error

set "QT_QPA_PLATFORM=windows"
start "" "%~dp0.venv\Scripts\pythonw.exe" -X utf8 "%~dp0STDF-Viewer.py" %* >>"logs\launcher.log" 2>&1
if errorlevel 1 goto launch_error
exit /b 0

:environment_error
echo [ERROR] The project's .venv Python environment is missing.
echo Set up the source environment as described in README_CN.md or README.md.
goto failed

:source_error
echo [ERROR] STDF-Viewer.py is missing. Keep this launcher in the Viewer source folder.
goto failed

:directory_error
echo [ERROR] Cannot access the Viewer folder or create its logs folder.
goto failed

:dependency_error
echo [ERROR] Viewer dependencies are unavailable in .venv.
type "logs\launcher-check.log"
echo See README_CN.md or README.md for dependency setup, including rust_stdf_helper.
goto failed

:launch_error
echo [ERROR] Could not start Viewer. See logs\launcher.log.

:failed
pause
exit /b 1
