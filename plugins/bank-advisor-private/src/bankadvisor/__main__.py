"""
CLI entry point for bankadvisor module commands.

Usage:
    python -m bankadvisor.etl_runner        # Run ETL manually
    python -m bankadvisor.etl_runner --cron # Run ETL (mark as cron-triggered)
"""
import sys

if __name__ == "__main__":
    # Check if specific submodule was requested
    if len(sys.argv) > 1 and "etl_runner" in sys.argv[0]:
        from bankadvisor.etl_runner import main
        main()
    else:
        print("BankAdvisor CLI")
        print("")
        print("Available commands:")
        print("  python -m bankadvisor.etl_runner        Run ETL pipeline")
        print("  python -m bankadvisor.etl_runner --cron Run ETL (cron mode)")
        sys.exit(0)
