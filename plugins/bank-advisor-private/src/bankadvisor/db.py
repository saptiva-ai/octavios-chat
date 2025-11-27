from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from core.config import get_settings

settings = get_settings()

# Construct PostgreSQL URL from settings (assuming you add these to Settings or env vars)
# Fallback to a default if not in settings for now, but ideally add to config.py
# Using a direct construction here based on the docker-compose values for now
POSTGRES_USER = "octavios" 
POSTGRES_PASSWORD = "secure_postgres_password"
POSTGRES_DB = "bankadvisor"
POSTGRES_HOST = "postgres"
POSTGRES_PORT = "5432"

DATABASE_URL = f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

engine = create_async_engine(DATABASE_URL, echo=settings.debug)
AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()

# Dependency for FastAPI routes if needed
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
