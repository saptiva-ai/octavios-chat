# ETL Data Status - BankAdvisor Plugin

**Last Updated**: 2025-11-27
**Status**: Schema Complete, Data Partially Populated

---

## Database Schema Status

### ✅ Columns Created (2025-11-27)

All required columns now exist in `monthly_kpis` table:

| Column | Data Type | Status | Notes |
|--------|-----------|--------|-------|
| `fecha` | timestamp | ✅ Populated | 206 records |
| `institucion` | text | ✅ Populated | 206 records |
| `banco_norm` | text | ✅ Populated | INVEX, SISTEMA |
| `cartera_total` | double precision | ✅ Populated | 206 records |
| `cartera_comercial_total` | double precision | ✅ Populated | 206 records |
| `cartera_consumo_total` | double precision | ✅ Populated | 206 records |
| `cartera_vivienda_total` | double precision | ✅ Populated | 206 records |
| `entidades_gubernamentales_total` | double precision | ✅ Populated | 206 records |
| `entidades_financieras_total` | double precision | ✅ Populated | 206 records |
| `empresarial_total` | double precision | ✅ Populated | 206 records |
| `cartera_vencida` | double precision | ✅ Populated | 206 records |
| `imor` | double precision | ✅ Populated | 206 records |
| `icor` | double precision | ✅ Populated | 206 records |
| `reservas_etapa_todas` | double precision | ✅ Populated | 206 records |
| **`tasa_mn`** | double precision | ⚠️ **Empty (0 records)** | **ETL pending** |
| **`tasa_me`** | double precision | ⚠️ **Empty (0 records)** | **ETL pending** |
| **`icap_total`** | double precision | ⚠️ **Empty (0 records)** | **ETL pending** |
| **`tda_cartera_total`** | double precision | ⚠️ **Empty (0 records)** | **ETL pending** |

### Migration Applied

**File**: `migrations/001_add_missing_columns.sql`

```sql
ALTER TABLE monthly_kpis
ADD COLUMN IF NOT EXISTS tasa_mn DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS tasa_me DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS icap_total DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS tda_cartera_total DOUBLE PRECISION;
```

**Executed**: 2025-11-27
**Result**: ✅ Success - 4 columns added

---

## Data Files Available

The following source files exist in `data/raw/` and contain data for the empty columns:

| File | Metric | Column Mapping | Status |
|------|--------|----------------|--------|
| `ICAP_Bancos.xlsx` | ICAP | → `icap_total` | ⚠️ Not loaded |
| `TDA.xlsx` | TDA | → `tda_cartera_total` | ⚠️ Not loaded |
| `CorporateLoan_CNBVDB.csv` | Tasas Corporativas | → `tasa_mn`, `tasa_me` | ⚠️ Not loaded |
| `TE_Invex_Sistema.xlsx` | Tasas Efectivas | → (reference data) | ⚠️ Not loaded |

---

## ETL Current State

### What Works ✅

The current ETL (`etl_loader.py`) successfully loads:
- Cartera metrics (total, comercial, consumo, vivienda)
- Calidad de cartera (IMOR, ICOR, cartera_vencida)
- Reservas
- Basic metadata (fecha, institucion, banco_norm)

**Source**: `CNBV_Cartera_Bancos_V2.xlsx`

### What's Missing ❌

The ETL has a TODO comment but doesn't implement loading for:

```python
# Line 45 in etl_loader.py:
# Agregar otras métricas (ICAP, TDA, Tasas) si existen en el source
```

**Impact**:
- Queries for ICAP, TDA, TASA_MN, TASA_ME will return empty results
- Parser accepts these queries (post-fix)
- SQL executes successfully but returns 0 rows

---

## Next Steps - ETL Enhancement

### Priority 1: ICAP Loading

**Source**: `data/raw/ICAP_Bancos.xlsx`

**Task**:
1. Add ICAP reader to `etl_loader.py`
2. Parse Excel structure
3. Join with existing monthly_kpis by (fecha, banco_norm)
4. UPDATE or INSERT icap_total values

**Estimated Effort**: 2-3 hours

**Sample Code**:
```python
def load_icap_data(file_path: str) -> pd.DataFrame:
    """Load ICAP data from Excel."""
    df = pd.read_excel(file_path, sheet_name='Sheet1')
    # TODO: Inspect actual Excel structure
    # Expected columns: Fecha, Banco, ICAP
    df_cleaned = df.rename(columns={
        'Fecha': 'fecha',
        'Banco': 'banco_norm',
        'ICAP': 'icap_total'
    })
    return df_cleaned
```

### Priority 2: TDA Loading

**Source**: `data/raw/TDA.xlsx`

**Task**:
1. Add TDA reader to `etl_loader.py`
2. Parse Excel structure
3. Join with monthly_kpis
4. UPDATE tda_cartera_total

**Estimated Effort**: 2-3 hours

### Priority 3: Tasas Loading

**Source**: `data/raw/CorporateLoan_CNBVDB.csv` (228 MB!)

**Task**:
1. Add CSV reader (large file - use chunking)
2. Filter for corporate loan rates
3. Separate MN vs ME
4. Join with monthly_kpis
5. UPDATE tasa_mn and tasa_me

**Estimated Effort**: 3-4 hours

**Challenges**:
- Large file (228 MB CSV)
- May need column mapping/filtering
- Potential data quality issues

---

## Workaround for Users

### Current Behavior

When users query ICAP, TDA, or Tasas:

1. ✅ Parser accepts query
2. ✅ SQL generated successfully
3. ✅ SQL validated and executed
4. ⚠️ **Result**: Empty dataset (0 rows)
5. ⚠️ **Frontend**: Shows empty chart with message

### Recommended User Message

When query returns 0 rows for these metrics:

```
"La métrica [ICAP/TDA/TASA_MN/TASA_ME] está configurada pero los datos históricos
aún no han sido cargados. Por favor contacta al equipo de datos para solicitar
la carga de esta métrica."
```

---

## Testing Plan

### Post-ETL Enhancement

Once data is loaded, test:

1. **ICAP Query**:
   ```
   Input: "ICAP del sistema últimos 6 meses"
   Expected: Line chart with ICAP values
   ```

2. **TDA Query**:
   ```
   Input: "TDA de INVEX en 2024"
   Expected: Timeline with TDA values
   ```

3. **Tasas Query**:
   ```
   Input: "tasa MN últimos 3 meses"
   Expected: Bar chart with interest rates
   ```

4. **Comparison**:
   ```
   Input: "compara ICAP de INVEX vs Sistema"
   Expected: Dual-line chart
   ```

---

## Migration Rollback (if needed)

If columns need to be removed:

```sql
ALTER TABLE monthly_kpis
DROP COLUMN IF EXISTS tasa_mn,
DROP COLUMN IF EXISTS tasa_me,
DROP COLUMN IF EXISTS icap_total,
DROP COLUMN IF EXISTS tda_cartera_total;
```

**Note**: Only run if ETL enhancement is cancelled. Otherwise, keep columns for future use.

---

## Summary

| Component | Status | Notes |
|-----------|--------|-------|
| DB Schema | ✅ Complete | 4 columns added successfully |
| QuerySpecParser | ✅ Updated | Now accepts ICAP, TDA, TASA_MN, TASA_ME |
| ETL Logic | ❌ Pending | Needs enhancement to load data |
| Data Files | ✅ Available | All source files exist in data/raw/ |
| User Impact | ⚠️ Partial | Queries accepted but return empty results |

**Recommendation**: Prioritize ETL enhancement for ICAP (most commonly requested metric).

---

**Last Verified**: 2025-11-27 via `SELECT COUNT(*) FROM monthly_kpis`
**Database**: PostgreSQL (Docker container: octavios-chat-bajaware_invex-postgres)
**Table**: `public.monthly_kpis`
**Total Rows**: 206
