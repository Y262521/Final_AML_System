@echo off
chcp 65001 > nul
cd /d "%~dp0"

set PYTHON_BIN=python
if exist "..\crypto-aml-tracker\backend-py\venv\Scripts\python.exe" (
    set PYTHON_BIN=..\crypto-aml-tracker\backend-py\venv\Scripts\python.exe
) else if exist "..\..\.venv\Scripts\python.exe" (
    set PYTHON_BIN=..\..\.venv\Scripts\python.exe
)

set PYTHONPATH=src;..\crypto-aml-tracker\backend-py\venv\Lib\site-packages

echo ============================================================
echo  LOAD PROCESSED TRANSACTIONS CSV TO MARIADB / MYSQL
echo ============================================================
echo.

%PYTHON_BIN% -m aml_pipeline.pipelines.run_load --cluster %*
echo.
echo Done.
