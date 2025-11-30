"""
ETL Runner with structured logging and execution tracking.

This module wraps the existing ETL processes (base + enhanced) with:
- Structured logging
- Execution tracking (stored in etl_runs table)
- Error handling and recovery
- Performance metrics

Usage:
    # Run manually
    python -m bankadvisor.etl_runner

    # Run from cron
    0 2 * * * cd /app && python -m bankadvisor.etl_runner >> /var/log/etl.log 2>&1
"""
import os
import sys
from datetime import datetime
from typing import Optional
import structlog
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Import existing ETL functions
from bankadvisor.etl_loader import run_etl as run_base_etl
from bankadvisor.etl_loader_enhanced import run_etl_enhancement
from bankadvisor.models.etl_run import ETLRun, Base as ETLBase
from core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()


def get_db_engine():
    """Get database engine with proper host resolution."""
    db_url = settings.database_url_sync

    # Override host if running outside docker
    if not os.path.exists("/.dockerenv"):
        db_url = db_url.replace(f"@{settings.postgres_host}:", "@localhost:")

    return create_engine(db_url)


def ensure_etl_runs_table_exists(engine):
    """
    Create etl_runs table if it doesn't exist.

    We use a separate Base to avoid circular imports with kpi.py.
    """
    logger.info("Ensuring etl_runs table exists...")
    ETLBase.metadata.create_all(engine)
    logger.info("etl_runs table ready")


def run_etl_once(triggered_by: str = "manual") -> Optional[int]:
    """
    Execute the complete ETL pipeline with tracking.

    This function:
    1. Creates an ETL run record with status='running'
    2. Executes base ETL (CNBV data → monthly_kpis)
    3. Executes enhanced ETL (ICAP, TDA, Tasas → monthly_kpis)
    4. Updates run record with results (success/failure)
    5. Logs structured metrics

    Args:
        triggered_by: Source of execution ('cron', 'manual', 'api')

    Returns:
        ETL run ID if successful, None if failed
    """
    engine = get_db_engine()
    ensure_etl_runs_table_exists(engine)

    Session = sessionmaker(bind=engine)
    session = Session()

    # Create run record
    etl_run = ETLRun(
        started_at=datetime.utcnow(),
        status="running",
        triggered_by=triggered_by,
        etl_version="1.0"  # Can be incremented when ETL logic changes
    )
    session.add(etl_run)
    session.commit()

    run_id = etl_run.id
    logger.info(
        "etl.started",
        run_id=run_id,
        triggered_by=triggered_by,
        started_at=etl_run.started_at.isoformat()
    )

    try:
        # =====================================================================
        # Phase 1: Base ETL (CNBV → monthly_kpis)
        # =====================================================================
        logger.info("etl.phase.base.started", run_id=run_id)
        run_base_etl()

        # Count rows inserted
        from sqlalchemy import text
        with engine.begin() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM monthly_kpis"))
            rows_base = result.scalar()

        etl_run.rows_processed_base = rows_base
        session.commit()

        logger.info(
            "etl.phase.base.completed",
            run_id=run_id,
            rows_processed=rows_base
        )

        # =====================================================================
        # Phase 2: Enhanced ETL (ICAP, TDA, Tasas)
        # =====================================================================
        logger.info("etl.phase.enhanced.started", run_id=run_id)
        run_etl_enhancement()

        # Count enriched columns
        with engine.begin() as conn:
            result = conn.execute(text("""
                SELECT
                    COUNT(icap_total) as icap_count,
                    COUNT(tda_cartera_total) as tda_count,
                    COUNT(tasa_mn) + COUNT(tasa_me) as tasas_count
                FROM monthly_kpis
            """))
            row = result.fetchone()
            icap_count = row[0]
            tda_count = row[1]
            tasas_count = row[2]

        etl_run.rows_processed_icap = icap_count
        etl_run.rows_processed_tda = tda_count
        etl_run.rows_processed_tasas = tasas_count
        session.commit()

        logger.info(
            "etl.phase.enhanced.completed",
            run_id=run_id,
            icap_rows=icap_count,
            tda_rows=tda_count,
            tasas_rows=tasas_count
        )

        # =====================================================================
        # Success: Mark run as completed
        # =====================================================================
        etl_run.completed_at = datetime.utcnow()
        etl_run.status = "success"
        etl_run.duration_seconds = (
            etl_run.completed_at - etl_run.started_at
        ).total_seconds()
        session.commit()

        logger.info(
            "etl.completed",
            run_id=run_id,
            status="success",
            duration_seconds=etl_run.duration_seconds,
            rows_base=rows_base,
            rows_icap=icap_count,
            rows_tda=tda_count,
            rows_tasas=tasas_count
        )

        return run_id

    except Exception as e:
        # =====================================================================
        # Failure: Log error and mark run as failed
        # =====================================================================
        etl_run.completed_at = datetime.utcnow()
        etl_run.status = "failure"
        etl_run.error_message = str(e)
        etl_run.duration_seconds = (
            etl_run.completed_at - etl_run.started_at
        ).total_seconds()
        session.commit()

        logger.error(
            "etl.failed",
            run_id=run_id,
            error=str(e),
            duration_seconds=etl_run.duration_seconds,
            exc_info=True
        )

        return None

    finally:
        session.close()


def main():
    """
    CLI entry point.

    Detects if running from cron vs manual execution.
    """
    # Determine trigger source
    if os.getenv("ETL_TRIGGER") == "cron":
        triggered_by = "cron"
    elif len(sys.argv) > 1 and sys.argv[1] == "--cron":
        triggered_by = "cron"
    else:
        triggered_by = "manual"

    logger.info("etl_runner.main.started", triggered_by=triggered_by)

    run_id = run_etl_once(triggered_by=triggered_by)

    if run_id:
        logger.info("etl_runner.main.success", run_id=run_id)
        sys.exit(0)
    else:
        logger.error("etl_runner.main.failure")
        sys.exit(1)


if __name__ == "__main__":
    main()
