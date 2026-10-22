@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo  Build Windows .exe (PyInstaller)
echo  Reimbursement Audit System v2.11.0
echo ============================================
echo.
echo Current dir: %cd%
echo.
echo Press any key to start...
pause >nul
echo.

set PYTHON_EXE=%cd%\python\python.exe
set APP_DIR=%cd%\workspace\reimbursement-app

if exist "%PYTHON_EXE%" goto python_ok
echo [ERROR] python\python.exe not found.
echo   Expected: %PYTHON_EXE%
echo   Run this from green package root.
pause
exit /b 1
:python_ok
echo [OK] Python: %PYTHON_EXE%
echo.

REM 1. 装 PyInstaller（如果还没装）
"%PYTHON_EXE%" -m PyInstaller --version >nul 2>&1
if errorlevel 1 goto need_install
echo [OK] PyInstaller already installed
goto step1_done
:need_install
echo [Step 1/3] Installing PyInstaller (from local wheels, no internet)...
"%PYTHON_EXE%" -m pip install --no-index --find-links=python\Lib\site-packages pyinstaller pyinstaller-hooks-contrib 2>&1
if errorlevel 1 goto pip_fail
echo [OK] PyInstaller installed
:step1_done
echo.

REM 2. Build Finance
echo [Step 2/3] Building Finance.exe (5-10 min)...
pushd "%APP_DIR%"
"%PYTHON_EXE%" -m PyInstaller --onefile --windowed --name "Finance" --add-data "templates;templates" --add-data "static;static" --hidden-import flask_sqlalchemy --hidden-import webview --hidden-import pythonnet --hidden-import clr_loader --hidden-import proxy_tools --hidden-import cv2 --hidden-import rapidocr_onnxruntime --collect-all pywebview --collect-all pythonnet --collect-all rapidocr_onnxruntime --noconfirm launcher_finance.py
if errorlevel 1 goto finance_fail
popd
echo [OK] Finance.exe built
echo.

REM 3. Build Auditor + Reimburser
echo [Step 3/3] Building Auditor.exe and Reimburser.exe...
pushd "%APP_DIR%"
"%PYTHON_EXE%" -m PyInstaller --onefile --windowed --name "Auditor" --add-data "templates;templates" --add-data "static;static" --collect-all pywebview --collect-all pythonnet --noconfirm launcher_auditor.py
if errorlevel 1 goto auditor_fail
"%PYTHON_EXE%" -m PyInstaller --onefile --windowed --name "Reimburser" --add-data "templates;templates" --add-data "static;static" --collect-all pywebview --collect-all pythonnet --noconfirm launcher_reimburser.py
if errorlevel 1 goto reimb_fail
popd

echo.
echo ============================================
echo  Build complete!
echo  Output: %APP_DIR%\dist\
echo    - Finance.exe
echo    - Auditor.exe
echo    - Reimburser.exe
echo ============================================
echo Each .exe is self-contained (150-200MB) and runs on Win7/10/11.
pause
exit /b 0

:pip_fail
echo.
echo [FAIL] pip install failed
pause
exit /b 1

:finance_fail
popd
echo.
echo [FAIL] Finance.exe build failed - check error above
pause
exit /b 1

:auditor_fail
popd
echo.
echo [FAIL] Auditor.exe build failed
pause
exit /b 1

:reimb_fail
popd
echo.
echo [FAIL] Reimburser.exe build failed
pause
exit /b 1
