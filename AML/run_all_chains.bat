@echo off
chcp 65001 > nul
cd /d "%~dp0"

set PYTHON_BIN=python
if exist "venv\Scripts\python.exe" (
    set PYTHON_BIN=venv\Scripts\python.exe
) else if exist "..\crypto-aml-tracker\backend-py\venv\Scripts\python.exe" (
    set PYTHON_BIN=..\crypto-aml-tracker\backend-py\venv\Scripts\python.exe
) else if exist "..\..\.venv\Scripts\python.exe" (
    set PYTHON_BIN=..\..\.venv\Scripts\python.exe
)

set PYTHONPATH=src;..\crypto-aml-tracker\backend-py\venv\Lib\site-packages

echo ============================================================
echo  HIGH-SPEED MULTI-CHAIN PIPELINE
echo  Runs: ETH, BNB, Polygon, Arbitrum, Base, BTC, LTC, DOGE, BCH, SOL
echo ============================================================
echo.

if "%~1"=="" (
    %PYTHON_BIN% run_all_chains.py
) else (
    %PYTHON_BIN% scripts\run_all_chains_etl.py %*
)
echo.
echo Done.

