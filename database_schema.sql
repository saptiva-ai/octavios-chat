-- ----------------------------------------------------------------------------
-- ESQUEMA DE BASE DE DATOS PARA ANALISIS FINANCIERO BANCARIO (NL2SQL READY)
-- ----------------------------------------------------------------------------

DROP TABLE IF EXISTS metricas_financieras;
DROP TABLE IF EXISTS instituciones;

-- Catalogo de instituciones
CREATE TABLE instituciones (
    id SERIAL PRIMARY KEY,
    nombre_oficial VARCHAR(255) UNIQUE NOT NULL,
    nombre_corto VARCHAR(100),
    es_sistema BOOLEAN DEFAULT FALSE
);

-- Hechos consolidados (Pm2 + Indicadores + CCT)
CREATE TABLE metricas_financieras (
    id SERIAL PRIMARY KEY,
    institucion_id INT REFERENCES instituciones(id) ON DELETE CASCADE,
    fecha_corte DATE NOT NULL,

    -- Balance general (millones de pesos)
    activo_total NUMERIC(20, 2),
    inversiones_financieras NUMERIC(20, 2),
    cartera_total NUMERIC(20, 2),
    captacion_total NUMERIC(20, 2),
    capital_contable NUMERIC(20, 2),
    resultado_neto NUMERIC(20, 2),

    -- Rentabilidad (%)
    roa_12m NUMERIC(10, 4),
    roe_12m NUMERIC(10, 4),

    -- Calidad de cartera (%)
    imor NUMERIC(10, 4),
    icor NUMERIC(10, 4),
    perdida_esperada NUMERIC(10, 4),

    CONSTRAINT uk_banco_fecha UNIQUE (institucion_id, fecha_corte)
);

-- Metadatos para NL2SQL
COMMENT ON TABLE metricas_financieras IS 'Tabla mensual de bancos mexicanos con balance, rentabilidad y calidad de cartera.';
COMMENT ON COLUMN metricas_financieras.activo_total IS 'Activos totales (MDP).';
COMMENT ON COLUMN metricas_financieras.cartera_total IS 'Cartera de credito total (MDP).';
COMMENT ON COLUMN metricas_financieras.resultado_neto IS 'Utilidad neta (MDP).';
COMMENT ON COLUMN metricas_financieras.roa_12m IS 'Retorno sobre activos (%).';
COMMENT ON COLUMN metricas_financieras.roe_12m IS 'Retorno sobre capital (%).';
COMMENT ON COLUMN metricas_financieras.imor IS 'Indice de morosidad (%).';
COMMENT ON COLUMN metricas_financieras.icor IS 'Indice de cobertura (%).';
