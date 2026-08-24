"""
run_wallet_tests.py

Queries the live backend (default http://localhost:4000/api) for each wallet
address in a CSV and compares the returned overall_risk against an expected
label, printing per-wallet results and a summary.

Accepts either CSV column format:
  - address, expected_label (bad/clean), source, notes   [older format]
  - address, ground_truth (BAD/CLEAN), category, name, chain, description

Usage:
  python run_wallet_tests.py <csv_file> [--base-url http://localhost:4000/api] [--threshold 0.55]
"""
import argparse
import csv
import sys
import time
import urllib.error
import urllib.request
import json


def load_wallets(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    wallets = []
    for row in rows:
        address = (row.get("address") or "").strip()
        if not address:
            continue
        raw_label = (row.get("expected_label") or row.get("ground_truth") or "").strip().lower()
        if raw_label not in ("bad", "clean"):
            print(f"  WARNING: skipping {address} -- unrecognized label {raw_label!r}", file=sys.stderr)
            continue
        source = row.get("source") or row.get("name") or row.get("category") or ""
        wallets.append({"address": address, "expected": raw_label, "source": source})
    return wallets


def fetch_risk(base_url, address, timeout=15):
    url = f"{base_url.rstrip('/')}/chain-of-custody/{address}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None, "NOT FOUND"
        return None, f"HTTP {e.code}"
    except urllib.error.URLError as e:
        return None, f"CONNECTION ERROR ({e.reason})"
    except Exception as e:
        return None, f"ERROR ({e})"

    risk = payload.get("overall_risk")
    stages_found = payload.get("stages_found") or []
    if risk is None or not stages_found:
        return None, "NOT FOUND"
    return risk, None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_file")
    parser.add_argument("--base-url", default="http://localhost:4000/api")
    parser.add_argument("--threshold", type=float, default=0.55)
    args = parser.parse_args()

    wallets = load_wallets(args.csv_file)
    print(f"Loaded {len(wallets)} test wallets from {args.csv_file}")
    print(f"Querying backend at {args.base_url} ...\n")

    results = []
    for idx, w in enumerate(wallets, 1):
        risk, err = fetch_risk(args.base_url, w["address"])
        short_addr = w["address"][:12] + "..."
        if err:
            print(f"[{idx}/{len(wallets)}] {short_addr} expected={w['expected']:<6} -> {err}")
            results.append({**w, "risk": None, "predicted": None})
        else:
            predicted = "bad" if risk >= args.threshold else "clean"
            print(f"[{idx}/{len(wallets)}] {short_addr} expected={w['expected']:<6} -> risk={risk}")
            results.append({**w, "risk": risk, "predicted": predicted})
        time.sleep(0.02)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    found = [r for r in results if r["risk"] is not None]
    not_found = [r for r in results if r["risk"] is None]

    print(f"Total wallets tested: {len(results)}")
    print(f"Not found in current pipeline data: {len(not_found)}")
    print(f"Found (had placement/layering/integration records): {len(found)}")

    correct = 0
    for r in found:
        match = r["predicted"] == r["expected"]
        correct += match
        mark = "\u2713" if match else "\u2717 MISMATCH"
        short_addr = r["address"][:12] + "..."
        print(f"  {short_addr} expected={r['expected']:<6} predicted={r['predicted']:<6} risk={r['risk']:.3f} {mark}")

    if found:
        print(f"\nOf the {len(found)} wallets WITH data:")
        print(f"  Correct: {correct}")
        print(f"  Wrong:   {len(found) - correct}")
        print(f"  Accuracy on tested subset: {100.0 * correct / len(found):.1f}%")

        bad_found = [r for r in found if r["expected"] == "bad"]
        clean_found = [r for r in found if r["expected"] == "clean"]
        if bad_found:
            recall = sum(1 for r in bad_found if r["predicted"] == "bad") / len(bad_found)
            print(f"  Recall on known-bad wallets:        {100.0*recall:.1f}%  ({len(bad_found)} tested)")
        if clean_found:
            fp_rate = sum(1 for r in clean_found if r["predicted"] == "bad") / len(clean_found)
            print(f"  False-positive rate on known-clean:  {100.0*fp_rate:.1f}%  ({len(clean_found)} tested)")

    if not_found:
        print(f"\nNot-found addresses (for reference):")
        for r in not_found:
            print(f"  {r['address']}  (expected={r['expected']}, source={r['source']})")


if __name__ == "__main__":
    main()
