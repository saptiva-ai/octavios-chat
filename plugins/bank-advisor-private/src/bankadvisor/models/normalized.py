"""
SQLAlchemy models for normalized banking schema.

These models correspond to the normalized schema defined in database_schema.sql:
- instituciones: Catalog of financial institutions
- metricas_financieras: Consolidated financial metrics (balance + income)
- segmentos_cartera: Catalog of portfolio segments (e.g., AUTOMOTRIZ, EMPRESAS)
- metricas_cartera_segmentada: Segmented portfolio metrics (IMOR/ICOR by segment)
"""
from sqlalchemy import Column, Integer, String, Date, Numeric, Boolean, ForeignKey, Text
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Institucion(Base):
    """Financial institution catalog."""
    __tablename__ = "instituciones"

    id = Column(Integer, primary_key=True)
    nombre_oficial = Column(String(255), unique=True, nullable=False, index=True)
    nombre_corto = Column(String(100))
    es_sistema = Column(Boolean, default=False)

    # Relationships
    metricas_financieras = relationship("MetricaFinanciera", back_populates="institucion")
    metricas_segmentadas = relationship("MetricaCarteraSegmentada", back_populates="institucion")


class MetricaFinanciera(Base):
    """Consolidated financial metrics per institution per month."""
    __tablename__ = "metricas_financieras"

    id = Column(Integer, primary_key=True)
    institucion_id = Column(Integer, ForeignKey("instituciones.id", ondelete="CASCADE"), nullable=False, index=True)
    fecha_corte = Column(Date, nullable=False, index=True)

    # Balance sheet (millions of pesos)
    activo_total = Column(Numeric(20, 2))
    inversiones_financieras = Column(Numeric(20, 2))
    cartera_total = Column(Numeric(20, 2))
    captacion_total = Column(Numeric(20, 2))
    capital_contable = Column(Numeric(20, 2))
    resultado_neto = Column(Numeric(20, 2))

    # Profitability (%)
    roa_12m = Column(Numeric(10, 4))
    roe_12m = Column(Numeric(10, 4))

    # Portfolio quality (%)
    imor = Column(Numeric(10, 4))
    icor = Column(Numeric(10, 4))
    perdida_esperada = Column(Numeric(10, 4))

    # Relationship
    institucion = relationship("Institucion", back_populates="metricas_financieras")


class SegmentoCartera(Base):
    """Portfolio segment catalog (normalized)."""
    __tablename__ = "segmentos_cartera"

    id = Column(Integer, primary_key=True)
    codigo = Column(String(50), unique=True, nullable=False, index=True)
    nombre = Column(String(100), nullable=False)
    descripcion = Column(Text)

    # Relationship
    metricas_segmentadas = relationship("MetricaCarteraSegmentada", back_populates="segmento")


class MetricaCarteraSegmentada(Base):
    """Segmented portfolio metrics (IMOR/ICOR by segment)."""
    __tablename__ = "metricas_cartera_segmentada"

    id = Column(Integer, primary_key=True)
    institucion_id = Column(Integer, ForeignKey("instituciones.id", ondelete="CASCADE"), nullable=False, index=True)
    segmento_id = Column(Integer, ForeignKey("segmentos_cartera.id", ondelete="CASCADE"), nullable=False, index=True)
    fecha_corte = Column(Date, nullable=False, index=True)
    cartera_total = Column(Numeric(20, 2))
    imor = Column(Numeric(10, 4))
    icor = Column(Numeric(10, 4))
    perdida_esperada = Column(Numeric(10, 4))

    # Relationships
    institucion = relationship("Institucion", back_populates="metricas_segmentadas")
    segmento = relationship("SegmentoCartera", back_populates="metricas_segmentadas")
