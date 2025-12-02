from sqlalchemy import Column, Integer, Float, String, Date, DateTime
from sqlalchemy.orm import declarative_base

# Use local Base to avoid circular import with db.py
Base = declarative_base()

class MonthlyKPI(Base):
    __tablename__ = "monthly_kpis"

    id = Column(Integer, primary_key=True, index=True)
    fecha = Column(Date, index=True)
    institucion = Column(String, index=True)
    
    # Carteras
    cartera_total = Column(Float)
    cartera_comercial_total = Column(Float)
    cartera_consumo_total = Column(Float)
    cartera_vivienda_total = Column(Float)
    entidades_gubernamentales_total = Column(Float)
    entidades_financieras_total = Column(Float)
    empresarial_total = Column(Float)

    # Calidad de Cartera
    cartera_vencida = Column(Float)
    imor = Column(Float)
    icor = Column(Float)
    
    # Reservas
    reservas_etapa_todas = Column(Float)
    reservas_variacion_mm = Column(Float, nullable=True)  # Variación mes a mes (%)

    # Pérdida Esperada (PE)
    pe_total = Column(Float, nullable=True)
    pe_empresarial = Column(Float, nullable=True)
    pe_consumo = Column(Float, nullable=True)
    pe_vivienda = Column(Float, nullable=True)

    # Etapas de Deterioro (ratios sobre cartera total)
    ct_etapa_1 = Column(Float, nullable=True)
    ct_etapa_2 = Column(Float, nullable=True)
    ct_etapa_3 = Column(Float, nullable=True)

    # Quebrantos Comerciales
    quebrantos_cc = Column(Float, nullable=True)
    quebrantos_vs_cartera_cc = Column(Float, nullable=True)  # Ratio quebrantos / cartera comercial

    # Tasas
    tasa_mn = Column(Float, nullable=True)
    tasa_me = Column(Float, nullable=True)
    icap_total = Column(Float, nullable=True)
    tda_cartera_total = Column(Float, nullable=True)
    tasa_sistema = Column(Float, nullable=True)  # Tasa Efectiva Sistema
    tasa_invex_consumo = Column(Float, nullable=True)  # Tasa Efectiva INVEX Consumo

    # Metadata
    banco_norm = Column(String, index=True)  # Nombre normalizado (ej: INVEX, BBVA)
