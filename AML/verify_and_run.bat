@echo off
chcp 65001 > nul
cd /d "%~dp0"

set PYTHON_BIN=python
if exist "..\crypto-aml-tracker\backend-py\venv\Scripts\python.exe" (
    set PYTHON_BIN=..\crypto-aml-tracker\backend-py\venv\Scripts\python.exe
) else if exist "..\..\.venv\Scripts\python.exe" (
    set PYTHON_BIN=..\..\.venv\Scripts\python.exe
)

echo Using correct AML directory: %CD%
echo.
echo Running ETL pipeline (3 blocks, skip-neo4j)...
%PYTHON_BIN% -c "import sys; sys.path.insert(0,'src'); from aml_pipeline.pipelines.run_etl import main; import sys; sys.argv=['run_etl','--batch','3','--skip-neo4j']; main()"

