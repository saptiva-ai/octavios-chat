"""
Database configuration for BankAdvisor MCP Server.

Uses SQLAlchemy async engine for PostgreSQL connections.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

from core.config import get_settings

settings = get_settings()

# Create async engine using settings
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10
)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Import Base from models to ensure single source of truth
from bankadvisor.models.kpi import Base


async def init_db():
    """
    Initialize database schema.
    Creates the monthly_kpis table if it doesn't exist.
    """
    async with engine.begin() as conn:
        # Create table if not exists
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS monthly_kpis (
                id SERIAL PRIMARY KEY,
                fecha TIMESTAMP,
                institucion VARCHAR(100),
                banco_norm VARCHAR(100),
                cartera_total NUMERIC,
                cartera_comercial_total NUMERIC,
                cartera_consumo_total NUMERIC,
                cartera_vivienda_total NUMERIC,
                entidades_gubernamentales_total NUMERIC,
                entidades_financieras_total NUMERIC,
                empresarial_total NUMERIC,
                cartera_vencida NUMERIC,
                imor NUMERIC,
                icor NUMERIC,
                reservas_etapa_todas NUMERIC,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))


async def get_db():
    """Dependency for FastAPI routes if needed."""
    async with AsyncSessionLocal() as session:
        yield session
