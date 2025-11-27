-- Migration: Add missing columns to monthly_kpis table
-- Date: 2025-11-27
-- Purpose: Add support for ICAP, TDA, and interest rate metrics

-- Add missing columns
ALTER TABLE monthly_kpis
ADD COLUMN IF NOT EXISTS tasa_mn DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS tasa_me DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS icap_total DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS tda_cartera_total DOUBLE PRECISION;

-- Add comments for documentation
COMMENT ON COLUMN monthly_kpis.tasa_mn IS 'Tasa promedio ponderada para créditos corporativos en Moneda Nacional (%)';
COMMENT ON COLUMN monthly_kpis.tasa_me IS 'Tasa promedio ponderada para créditos corporativos en Moneda Extranjera (%)';
COMMENT ON COLUMN monthly_kpis.icap_total IS 'Índice de Capitalización - promedio ponderado por cartera (%)';
COMMENT ON COLUMN monthly_kpis.tda_cartera_total IS 'Tasa de Deterioro Ajustada de la cartera - promedio ponderado (%)';

-- Verify columns were added
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'monthly_kpis'
  AND column_name IN ('tasa_mn', 'tasa_me', 'icap_total', 'tda_cartera_total')
ORDER BY column_name;
