import sys
import uuid
from pathlib import Path

# Add AML src and backend-py to path
aml_root = Path(__file__).resolve().parents[1]
aml_src = aml_root / "src"
if str(aml_src) not in sys.path:
    sys.path.insert(0, str(aml_src))

from dotenv import load_dotenv
load_dotenv(aml_root / ".env")

# We import the route functions directly for the CLI so we don't have to spin up the server
backend_path = aml_root.parent / "crypto-aml-tracker" / "backend-py"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

backend_venv_pkg = backend_path / "venv" / "Lib" / "site-packages"
if backend_venv_pkg.exists() and str(backend_venv_pkg) not in sys.path:
    sys.path.insert(0, str(backend_venv_pkg))

from routes.testing import (
    _run_entity_tests, 
    _run_placement_tests, 
    _run_layering_tests, 
    _run_integration_tests, 
    _run_pipeline_test
)

def run_cli_tests():
    print("=" * 50)
    print("CRYPTO AML SYSTEM TEST")
    print("=" * 50)
    
    test_run_id = str(uuid.uuid4())
    all_tests = []
    
    # 1. Entity Resolution
    print("\nENTITY RESOLUTION")
    entity_tests = _run_entity_tests(test_run_id)
    all_tests.extend(entity_tests)
    for t in entity_tests:
        status = "[PASS]" if t["passed"] else "[FAIL]"
        print(f"{status} {t['scenario']}")

    # 2. Placement
    print("\nPLACEMENT")
    placement_tests = _run_placement_tests(test_run_id)
    all_tests.extend(placement_tests)
    for t in placement_tests:
        status = "[PASS]" if t["passed"] else "[FAIL]"
        print(f"{status} {t['scenario']}")

    # 3. Layering
    print("\nLAYERING")
    layering_tests = _run_layering_tests(test_run_id)
    all_tests.extend(layering_tests)
    for t in layering_tests:
        status = "[PASS]" if t["passed"] else "[FAIL]"
        print(f"{status} {t['scenario']}")

    # 4. Integration
    print("\nINTEGRATION")
    integration_tests = _run_integration_tests(test_run_id)
    all_tests.extend(integration_tests)
    for t in integration_tests:
        status = "[PASS]" if t["passed"] else "[FAIL]"
        print(f"{status} {t['scenario']}")

    # 5. End-to-end
    print("\nEND-TO-END")
    pipeline_tests = _run_pipeline_test(test_run_id)
    all_tests.extend(pipeline_tests)
    for t in pipeline_tests:
        status = "[PASS]" if t["passed"] else "[FAIL]"
        print(f"{status} {t['scenario']}")

    print("\n" + "=" * 50)
    print("RESULT")
    print("=" * 50)
    
    passed = sum(1 for t in all_tests if t["passed"])
    failed = len(all_tests) - passed
    
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Errors: 0")
    print(f"Pass Rate: {int(passed / len(all_tests) * 100)}%")
    print("=" * 50)
    
    if failed > 0:
        sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    run_cli_tests()
