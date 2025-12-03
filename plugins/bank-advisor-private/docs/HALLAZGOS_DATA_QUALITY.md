# Hallazgos Críticos: Calidad de Datos BankAdvisor

**Fecha**: 2025-12-03
**Score General**: 73.9/100
**Estado**: ❌ 6 problemas críticos identificados

---

## 📊 Resumen Ejecutivo

Se ejecutó validación completa de integridad de datos sobre 7 métricas × 7 bancos = 49 validaciones.

**Distribución de Calidad**:
- ✅ **Buena (≥80)**: 24/49 (49%)
- 🟡 **Aceptable (60-79)**: 13/49 (27%)
- 🟠 **Warning (40-59)**: 6/49 (12%)
- 🔴 **Crítica (<40)**: 6/49 (12%)

---

## 🔴 Problemas Críticos (P0) - Requieren Acción Inmediata

### 1. ICOR: Valores Negativos Fuera de Rango

**Score**: 0/100 para todos los bancos (INVEX, SISTEMA, SANTANDER, BANORTE, HSBC, CITIBANAMEX)

**Problema**:
```
Expected Range: 0 - 500 %
Actual Range: -2.21 to -0.31 (103/103 valores negativos)
Latest Value (INVEX): -1.09%
```

**Causa Raíz**:
- ICOR (Índice de Cobertura) está almacenado como **valor negativo** en la DB
- Validación esperaba 0-500% (cobertura típica 100-200%)
- **TODOS** los 103 valores históricos están negativos para todos los bancos

**Implicaciones**:
- Visualizaciones muestran valores negativos (incorrectos)
- Usuario ve "ICOR de INVEX: -1.09%" → **no tiene sentido**
- Comparaciones inválidas

**Acción Requerida**:
1. **Investigar fuente de datos**: ¿Por qué ICOR es negativo en ETL?
   ```python
   # Verificar transformación en etl/polars_transform.py
   # ¿Se está invirtiendo el signo incorrectamente?
   ```

2. **Opción A** (si datos son correctos negativos):
   - Actualizar rango esperado a `-500 to 0`
   - Cambiar visualización para mostrar valor absoluto
   - Actualizar documentación: "ICOR negativo indica..."

3. **Opción B** (más probable - error de transformación):
   - Corregir ETL para invertir signo: `icor_abs = abs(icor)`
   - Re-ejecutar ETL histórico
   - Validar que valores queden en 0-500%

**Prioridad**: 🔴 **CRÍTICA** - Datos inválidos en producción

---

### 2. ICAP: 100% Valores en Zero

**Score**: 70/100 para 6/7 bancos (solo penalty por zeros)

**Problema**:
```
Expected Range: 0 - 30 %
Actual Range: 0.00 - 0.00 (100% de 103 valores = 0)
Latest Value: 0.00%
```

**Bancos afectados**: INVEX, SISTEMA, SANTANDER, BANORTE, HSBC, CITIBANAMEX

**Causa Raíz**:
- Columna `icap_total` existe pero **todos los valores son 0.00**
- Script de validación previo reportó "89.2% cobertura" pero valores son zeros, no NULLs
- ETL no está cargando datos de ICAP correctamente

**Implicaciones**:
- Queries como "ICAP de INVEX" retornan línea plana en 0
- Usuario no puede analizar capitalización
- Visualización inútil

**Acción Requerida**:
1. **Verificar fuente de datos CNBV**:
   ```sql
   -- ¿CNBV reporta ICAP como columna separada?
   SELECT DISTINCT column_name FROM cnbv_raw_data WHERE column_name LIKE '%cap%';
   ```

2. **Revisar transformación ETL**:
   ```python
   # En etl/polars_transform.py
   # Buscar cálculo de icap_total
   # ¿Fórmula correcta? ¿Columna fuente correcta?
   ```

3. **Opciones**:
   - **Si CNBV no tiene ICAP**: Eliminar métrica o calcular a partir de otras columnas
   - **Si está en otro campo**: Mapear campo correcto en ETL
   - **Si cálculo está mal**: Corregir fórmula

**Prioridad**: 🔴 **CRÍTICA** - Métrica nueva anunciada pero sin datos

---

## 🟠 Problemas Importantes (P1)

### 3. BBVA: Sin Datos para Ninguna Métrica

**Score**: 50/100 (100% NULLs en todas las métricas)

**Problema**:
```
BBVA tiene 75 registros pero:
- IMOR: 100% NULL
- ICOR: 100% NULL
- ICAP: 100% NULL
- TDA: 100% NULL
- TASA_MN: 100% NULL
- TASA_ME: 100% NULL

Única métrica con datos: Cartera Total (pero 100% zeros)
```

**Fecha de datos**: Última fecha 2023-04-01 (hace 2 años!)

**Causa Raíz**:
- BBVA dejó de sincronizarse en abril 2023
- ETL no está cargando datos recientes de BBVA
- Posiblemente cambio en formato de reporte CNBV

**Implicaciones**:
- Comparaciones "INVEX vs BBVA" fallan o muestran datos desactualizados
- Usuario espera datos actuales pero obtiene de hace 2 años

**Acción Requerida**:
1. **Verificar logs de ETL para BBVA**:
   ```bash
   grep "BBVA" logs/etl_*.log | tail -50
   ```

2. **Revisar mapeo de nombres**:
   ```python
   # ¿CNBV cambió nombre de "BBVA" a "BBVA BANCOMER" o "BBVA MÉXICO"?
   # Verificar BANK_ALIASES en etl/bank_normalizer.py
   ```

3. **Re-ejecutar ETL con logs debug** para BBVA

**Prioridad**: 🟠 **ALTA** - Banco importante sin datos

---

### 4. TDA: 91.3% Valores en Zero

**Score**: 73/100 para todos los bancos

**Problema**:
```
Expected Range: 0 - 100 %
Actual Data: 91.3% de valores = 0.00
Non-zero Range: 0 - 6.91%
Latest Value: 0.00%
```

**Análisis**:
- TDA solo tiene valores != 0 en ~9 meses de 103 (2019-2020 principalmente)
- Últimos 5+ años: todos 0.00
- Métrica parece estar obsoleta o mal calculada

**Causa Raíz Posible**:
- TDA (Tasa de Deterioro Ajustada) puede ser métrica calculada compleja
- Fórmula puede depender de campos que ya no existen en CNBV
- O métrica solo aplicaba a cierto periodo regulatorio

**Implicaciones**:
- Queries "TDA de INVEX" muestran línea plana en 0 (últimos años)
- Solo datos históricos 2019-2020 tienen valores

**Acción Requerida**:
1. **Investigar definición de TDA**:
   - ¿Métrica actual o histórica?
   - ¿CNBV sigue requiriendo reporte?

2. **Opciones**:
   - **Si obsoleta**: Marcar como "histórica" en metadata, agregar warning en UI
   - **Si actual**: Corregir cálculo en ETL

3. **Comunicar al usuario**: "TDA solo disponible para 2019-2020"

**Prioridad**: 🟠 **MEDIA** - Métrica con datos pero limitados

---

### 5. Cartera Total BBVA: 100% Zeros

**Score**: 70/100

**Problema**:
- BBVA tiene 75 registros de cartera_total pero todos son 0.00
- Otros bancos tienen valores válidos (INVEX: 1,775 MDP, SISTEMA: 3.1M MDP)

**Relacionado con**: Problema #3 (BBVA sin datos)

**Acción**: Misma que #3

---

## 🟡 Warnings (P2)

### 6. TASA_MN: Posible Problema de Unidades

**Score**: 92.6/100 (aceptable pero revisar)

**Observación**:
```
Expected Range: 0 - 50 %
Actual Range: 0 - 20.60%
Mean: 10.16%
Latest (INVEX): 18.38%
```

**Estado**: ✅ Dentro de rango, pero en testing manual vimos:
- "TASA_MN de INVEX" retornó 1838.14 (valor * 100?)

**Requiere Verificación**:
1. ¿DB almacena en % (18.38) o basis points (1838)?
2. ¿Transformación inconsistente entre ETL y query engine?

**Acción**: Verificar consulta directa:
```sql
SELECT fecha, tasa_mn FROM monthly_kpis WHERE banco_norm='INVEX' ORDER BY fecha DESC LIMIT 5;
```

---

## ✅ Métricas con Calidad Excelente

### IMOR (Índice de Morosidad)
- **Score**: 98.6/100 promedio
- **Cobertura**: 100% para 6/7 bancos
- **Rango**: 7.12 - 215.22% (dentro de esperado)
- **Última actualización**: 2025-07-01

### Cartera Total
- **Score**: 95.7/100 promedio
- **Cobertura**: 100% para 6/7 bancos
- **Datos válidos y actualizados**

### TASA_MN y TASA_ME
- **Score**: 92.6/100 promedio
- **Cobertura**: 100% para 6/7 bancos
- **Solo ~1-3% zeros (aceptable)**

---

## 📋 Plan de Acción Priorizado

### Esta Semana (P0)

1. **ICOR Negativo** (4h)
   - [ ] Investigar transformación ETL
   - [ ] Corregir signo o rango esperado
   - [ ] Validar datos corregidos
   - [ ] Re-ejecutar ETL si necesario

2. **ICAP Zeros** (4h)
   - [ ] Verificar fuente CNBV
   - [ ] Corregir mapeo/cálculo en ETL
   - [ ] Validar datos reales
   - [ ] Si no disponible: Eliminar métrica o marcar como "no soportada"

3. **Data Quality Warnings en API** (2h)
   - [ ] Implementar warnings en response metadata
   - [ ] Agregar `data_quality_score` por banco/métrica
   - [ ] Mostrar mensaje cuando score < 60

### Próxima Semana (P1)

4. **BBVA Sin Datos** (3h)
   - [ ] Diagnosticar ETL logs
   - [ ] Corregir mapeo de nombres
   - [ ] Re-sincronizar desde abril 2023

5. **TDA Investigación** (2h)
   - [ ] Documentar si métrica es histórica
   - [ ] Agregar nota en UI
   - [ ] Considerar remover si obsoleta

### Mejoras Futuras (P2)

6. **TASA Normalización** (1h)
7. **Automated Data Quality Alerts** (3h)
8. **ETL Monitoring Dashboard** (4h)

---

## 🎯 Métricas de Éxito

**Objetivo**: Score General ≥ 90/100

**Targets por Métrica**:
| Métrica | Actual | Target |
|---------|--------|--------|
| IMOR | 98.6 ✅ | 95 |
| ICOR | **7.1** 🔴 | 95 |
| ICAP | **67.1** 🟠 | 90 |
| TDA | 69.4 🟠 | 85 |
| TASA_MN | 92.6 ✅ | 90 |
| TASA_ME | 85.7 ✅ | 85 |
| Cartera | 95.7 ✅ | 95 |

**Bloqueadores para Producción**:
- 🔴 ICOR con valores negativos (usuario reportará como bug)
- 🔴 ICAP con zeros (métrica anunciada pero no funciona)

**Recomendación**: **No promover a producción** hasta resolver P0s.

---

## 📞 Contactos y Seguimiento

**Responsable Data Quality**: [TBD]
**ETL Owner**: [TBD]
**Fecha Revisión**: 2025-12-03
**Próxima Validación**: 2025-12-10 (después de fixes)
