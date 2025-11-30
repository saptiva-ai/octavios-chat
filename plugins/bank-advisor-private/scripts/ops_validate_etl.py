#!/usr/bin/env python3
"""
ETL Operations Validator - BankAdvisor

Validates that ETL is running correctly and data is fresh.
Use this script before demos or as part of monitoring.

Usage:
    python scripts/ops_validate_etl.py
    python scripts/ops_validate_etl.py --port 8002 --max-age-hours 36

Exit codes:
    0 = ETL healthy and data fresh
    1 = ETL issues detected
"""
import argparse
import sys
from datetime import datetime, timezone
from typing import List, Tuple
import requests


def parse_args():
    parser = argparse.ArgumentParser(description="Validate ETL health")
    parser.add_argument("--host", default="localhost", help="Server host")
    parser.add_argument("--port", type=int, default=8002, help="Server port")
    parser.add_argument(
        "--max-age-hours",
        type=int,
        default=36,
        help="Max hours since last successful ETL (default: 36)"
    )
    return parser.parse_args()


def validate_etl(base_url: str, max_age_hours: int) -> Tuple[bool, List[str]]:
    """
    Validate ETL health and data freshness.

    Returns:
        (success, list of messages)
    """
    issues = []
    info = []

    try:
        response = requests.get(f"{base_url}/health", timeout=10)

        if response.status_code != 200:
            return False, [f"Health endpoint returned {response.status_code}"]

        health = response.json()

        # Check server status
        if health.get("status") != "healthy":
            issues.append(f"Server status: {health.get('status')}")
        else:
            info.append(f"Server status: healthy")

        # Check ETL info
        etl = health.get("etl", {})

        if not etl:
            issues.append("No ETL info in healthcheck (etl_runs table may not exist)")
            return False, issues

        # Check last run status
        last_status = etl.get("last_run_status")
        if last_status == "success":
            info.append(f"Last ETL status: success")
        elif last_status == "failure":
            issues.append(f"Last ETL FAILED: {etl.get('error_message', 'unknown')}")
        elif last_status == "never_run":
            issues.append("ETL has never run - no data in database")
        else:
            issues.append(f"Unknown ETL status: {last_status}")

        # Check data freshness
        last_completed = etl.get("last_run_completed")
        if last_completed and last_status == "success":
            try:
                # Parse timestamp (handle both formats)
                if "Z" in last_completed:
                    last_dt = datetime.fromisoformat(last_completed.replace("Z", "+00:00"))
                elif "+" in last_completed:
                    last_dt = datetime.fromisoformat(last_completed)
                else:
                    last_dt = datetime.fromisoformat(last_completed).replace(tzinfo=timezone.utc)

                now = datetime.now(timezone.utc)
                age_hours = (now - last_dt).total_seconds() / 3600

                info.append(f"Last successful ETL: {last_completed}")
                info.append(f"Data age: {age_hours:.1f} hours")

                if age_hours > max_age_hours:
                    issues.append(
                        f"Data is STALE: {age_hours:.1f} hours old (max: {max_age_hours}h)"
                    )
                else:
                    info.append(f"Data freshness: OK (< {max_age_hours}h)")

            except Exception as e:
                issues.append(f"Cannot parse ETL timestamp: {e}")

        # Check rows processed
        rows = etl.get("last_run_rows", 0)
        if rows > 0:
            info.append(f"Rows in last ETL: {rows}")
        elif last_status == "success":
            issues.append("Warning: Last ETL reported 0 rows")

        # Check duration
        duration = etl.get("last_run_duration_seconds", 0)
        if duration > 0:
            info.append(f"Last ETL duration: {duration:.1f}s")

        return len(issues) == 0, info + issues

    except requests.exceptions.ConnectionError:
        return False, [f"Cannot connect to {base_url}"]
    except Exception as e:
        return False, [f"Validation failed: {str(e)}"]


def main():
    args = parse_args()
    base_url = f"http://{args.host}:{args.port}"

    print("=" * 60)
    print("🔍 ETL OPERATIONS VALIDATOR - BankAdvisor")
    print("=" * 60)
    print(f"Target: {base_url}")
    print(f"Max data age: {args.max_age_hours} hours")
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")
    print("-" * 60)

    success, messages = validate_etl(base_url, args.max_age_hours)

    for msg in messages:
        if any(word in msg.lower() for word in ["fail", "stale", "error", "warning", "never"]):
            print(f"❌ {msg}")
        else:
            print(f"✅ {msg}")

    print("-" * 60)

    if success:
        print("🟢 ETL HEALTHY - Data is fresh and ready")
        sys.exit(0)
    else:
        print("🔴 ETL ISSUES DETECTED - Review before demo")
        sys.exit(1)


if __name__ == "__main__":
    main()
