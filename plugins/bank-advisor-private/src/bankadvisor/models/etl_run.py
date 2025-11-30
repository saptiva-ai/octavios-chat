"""
ETL Run tracking model for monitoring automated ETL executions.

This model stores metadata about each ETL run to enable:
- Healthcheck reporting (last successful run)
- ETL history and debugging
- Performance monitoring
"""
from sqlalchemy import Column, Integer, String, DateTime, Float, Text
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()


class ETLRun(Base):
    """
    Tracks individual ETL executions.

    Each record represents one complete ETL run (base + enhanced).
    """
    __tablename__ = "etl_runs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # Timing
    started_at = Column(DateTime, nullable=False, index=True)
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)

    # Status
    status = Column(String(20), nullable=False, index=True)  # 'success', 'failure', 'running'
    error_message = Column(Text, nullable=True)

    # Metrics
    rows_processed_base = Column(Integer, nullable=True)  # From base ETL
    rows_processed_icap = Column(Integer, nullable=True)
    rows_processed_tda = Column(Integer, nullable=True)
    rows_processed_tasas = Column(Integer, nullable=True)

    # Metadata
    etl_version = Column(String(50), nullable=True)  # For future versioning
    triggered_by = Column(String(50), default="manual")  # 'cron', 'manual', 'api'

    def __repr__(self):
        return f"<ETLRun(id={self.id}, started_at={self.started_at}, status={self.status})>"
