"""DevTools AML Audit API route — provides 12-algorithm testing and reporting."""

from __future__ import annotations

import csv
import io
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File
import pandas as pd

router = APIRouter()
logger = logging.getLogger(__name__)

# Import the 12-algorithm audit engine from AML
try:
    import sys, os
    AML_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../AML"))
    if AML_PATH not in sys.path:
        sys.path.insert(0, AML_PATH)
    from test_12_algorithms import AML12AlgorithmAuditEngine
except Exception as e:
    logger.warning("Could not import AML12AlgorithmAuditEngine directly: %s", e)
    AML12AlgorithmAuditEngine = None


@router.get("/benchmark-report")
async def get_benchmark_report():
    """Return pre-computed 12-algorithm benchmark audit report on standard test suite."""
    if AML12AlgorithmAuditEngine is None:
        raise HTTPException(status_code=500, detail="Audit engine unavailable")
    
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../AML"))
    data_csv = os.path.join(base_dir, "all_12_aml_algorithms_mock_data.csv")
    wallets_csv = os.path.join(base_dir, "all_12_aml_algorithms_mock_wallets.csv")
    
    if not os.path.exists(data_csv):
        raise HTTPException(status_code=404, detail="Benchmark dataset not found")
        
    df_tx = pd.read_csv(data_csv)
    df_wallets = pd.read_csv(wallets_csv) if os.path.exists(wallets_csv) else None
    
    engine = AML12AlgorithmAuditEngine(df_tx, df_wallets)
    report = engine.run_full_audit()
    return report


@router.post("/audit-csv")
async def audit_uploaded_csv(file: UploadFile = File(...)):
    """Accept an uploaded CSV file of transactions, run all 12 AML algorithms, and return the audit report."""
    if AML12AlgorithmAuditEngine is None:
        raise HTTPException(status_code=500, detail="Audit engine unavailable")
        
    contents = await file.read()
    try:
        df_tx = pd.read_csv(io.StringIO(contents.decode("utf-8")))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid CSV format: {e}")
        
    engine = AML12AlgorithmAuditEngine(df_tx, None)
    report = engine.run_full_audit()
    return report
