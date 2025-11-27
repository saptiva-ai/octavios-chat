from sqlalchemy import Column, Integer, Float, String, Date, DateTime
from bankadvisor.db import Base

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
    
    # Tasas
    tasa_mn = Column(Float, nullable=True)
    tasa_me = Column(Float, nullable=True)
    icap_total = Column(Float, nullable=True)
    tda_cartera_total = Column(Float, nullable=True)
    
    # Metadata
    banco_norm = Column(String, index=True)  # Nombre normalizado (ej: INVEX, BBVA)
