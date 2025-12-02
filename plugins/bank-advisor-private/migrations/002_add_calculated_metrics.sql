-- Migration: Add calculated metrics columns to monthly_kpis table
-- Date: 2025-12-01
-- Purpose: Add support for PE, reservas variation, etapas deterioro, quebrantos, and TE metrics

-- Add Pérdida Esperada (PE) columns
ALTER TABLE monthly_kpis
ADD COLUMN IF NOT EXISTS pe_total DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS pe_empresarial DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS pe_consumo DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS pe_vivienda DOUBLE PRECISION;

-- Add Reservas variation column
ALTER TABLE monthly_kpis
ADD COLUMN IF NOT EXISTS reservas_variacion_mm DOUBLE PRECISION;

-- Add Etapas de Deterioro columns
ALTER TABLE monthly_kpis
ADD COLUMN IF NOT EXISTS ct_etapa_1 DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS ct_etapa_2 DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS ct_etapa_3 DOUBLE PRECISION;

-- Add Quebrantos columns
ALTER TABLE monthly_kpis
ADD COLUMN IF NOT EXISTS quebrantos_cc DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS quebrantos_vs_cartera_cc DOUBLE PRECISION;

-- Add Tasa Efectiva (TE) columns
ALTER TABLE monthly_kpis
ADD COLUMN IF NOT EXISTS tasa_sistema DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS tasa_invex_consumo DOUBLE PRECISION;

-- Add comments for documentation
COMMENT ON COLUMN monthly_kpis.pe_total IS 'Pérdida Esperada Total - ratio reservas/cartera total';
COMMENT ON COLUMN monthly_kpis.pe_empresarial IS 'Pérdida Esperada Empresarial - ratio reservas/cartera empresarial';
COMMENT ON COLUMN monthly_kpis.pe_consumo IS 'Pérdida Esperada Consumo - ratio reservas/cartera consumo';
COMMENT ON COLUMN monthly_kpis.pe_vivienda IS 'Pérdida Esperada Vivienda - ratio reservas/cartera vivienda';
COMMENT ON COLUMN monthly_kpis.reservas_variacion_mm IS 'Variación mes a mes de reservas totales (%)';
COMMENT ON COLUMN monthly_kpis.ct_etapa_1 IS 'Cartera Etapa 1 como ratio de cartera total (performing)';
COMMENT ON COLUMN monthly_kpis.ct_etapa_2 IS 'Cartera Etapa 2 como ratio de cartera total (watchlist)';
COMMENT ON COLUMN monthly_kpis.ct_etapa_3 IS 'Cartera Etapa 3 como ratio de cartera total (non-performing)';
COMMENT ON COLUMN monthly_kpis.quebrantos_cc IS 'Quebrantos de cartera comercial (write-offs)';
COMMENT ON COLUMN monthly_kpis.quebrantos_vs_cartera_cc IS 'Ratio quebrantos vs cartera comercial total';
COMMENT ON COLUMN monthly_kpis.tasa_sistema IS 'Tasa de Interés Efectiva del Sistema Bancario (%)';
COMMENT ON COLUMN monthly_kpis.tasa_invex_consumo IS 'Tasa de Interés Efectiva INVEX Consumo (%)';

-- Verify columns were added
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'monthly_kpis'
  AND column_name IN (
    'pe_total', 'pe_empresarial', 'pe_consumo', 'pe_vivienda',
    'reservas_variacion_mm',
    'ct_etapa_1', 'ct_etapa_2', 'ct_etapa_3',
    'quebrantos_cc', 'quebrantos_vs_cartera_cc',
    'tasa_sistema', 'tasa_invex_consumo'
  )
ORDER BY column_name;
