# Deploy Notes - Gráficas con Unidades y Canvas Improvements

## Resumen de Cambios (develop → prod)

### Features Principales:

#### 1. Unidades en Gráficas (MDP y %)
- ✅ Tooltips muestran unidades: "Valor: 1,500.00 MDP" o "Valor: 2.30%"
- ✅ Título del eje Y muestra: "MDP (Millones de Pesos)" o "%"
- ✅ Formato automático de Plotly.js para eje Y (sin redondeos extraños)

#### 2. Estadísticas Inyectadas en Contexto LLM
- ✅ Extrae min, max, avg, tendencia, cambio % de cada banco
- ✅ Optimiza contexto: ~200 tokens vs ~2000 tokens del plotly_config completo
- ✅ LLM ahora puede analizar y comparar valores entre bancos

#### 3. Canvas Auto-Close en Cambio de Conversación
- ✅ Canvas se cierra automáticamente al cambiar de conversación
- ✅ Estado del canvas vinculado al ID de conversación
- ✅ No persiste contenido de otras conversaciones

#### 4. SQL al Final del Mensaje
- ✅ Query SQL ahora aparece al final del mensaje del LLM
- ✅ Formato mejorado con bloques de código

### Archivos Modificados:

**Backend:**
- `apps/backend/src/routers/chat/handlers/streaming_handler.py`
  - Nueva función `_extract_chart_statistics()`
  - Inyección de estadísticas en contexto LLM
  - SQL movido al final del mensaje

**Bank Advisor Plugin:**
- `plugins/bank-advisor-private/src/bankadvisor/services/analytics_service.py`
  - Hovertemplates con unidades
  - Conversión de ratios a porcentaje (* 100)
  - Debug logging para tracking
  
- `plugins/bank-advisor-private/src/bankadvisor/services/visualization_service.py`
  - Hovertemplates con unidades
  - Formato automático de eje Y (sin tickformat/ticksuffix)
  
- `plugins/bank-advisor-private/src/main.py`
  - metric_type en metadata (ambos pipelines: HU3 y NL2SQL)
  - Conversión de valores en NL2SQL pipeline

**Frontend:**
- `apps/web/src/app/chat/_components/ChatView.tsx`
  - Auto-cierre del canvas al cambiar conversación
  - Estado del canvas por conversación ID

### Commits Incluidos:
```
b1080560 fix: Remove tickformat and ticksuffix from Y-axis, let Plotly auto-format
6dfdf01d feat: Auto-close canvas when switching conversations
701003bb fix: Remove currency division - DB values already in millions
ee3e766e fix: Add value conversion in NL2SQL pipeline
d28b2270 fix: Use .0f for Y-axis and ,.2f for tooltip to prevent duplicates
db1e9605 fix: Use .2f tickformat for all metrics to show Y-axis values correctly
3aaa0348 fix: Convert currency values to millions (MDP) in analytics_service
18e9c2e5 feat: Add chart units (MDP/%), statistics injection, and fix tickformat
```

### Testing Pre-Deploy:
- [ ] Tests en progreso...
- [ ] Verificar gráficas con métricas de ratio (IMOR, ICOR, ICAP)
- [ ] Verificar gráficas con métricas de monto (Cartera Comercial)
- [ ] Verificar auto-cierre del canvas al cambiar conversación
- [ ] Verificar que SQL aparece al final del mensaje

### Comandos para Deploy:
```bash
# Deploy a demo
make deploy ENV=demo

# Deploy a producción
make deploy ENV=prod
```

### Rollback Plan:
Si hay problemas en producción, revertir a commit:
```bash
git revert b1080560..HEAD
# O hacer checkout al commit anterior estable
```

### Notas Importantes:
- Los valores en la DB ya están en millones (MDP), NO dividir por 1,000,000
- Los ratios vienen como decimales (0.023 = 2.3%), multiplicar por 100
- Plotly.js maneja el formato automático del eje Y (no especificar tickformat)
