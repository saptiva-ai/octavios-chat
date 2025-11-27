# Análisis SOLID - BankAdvisor MCP Server

## 🔍 Violaciones Identificadas

### 1. **SRP (Single Responsibility Principle)** ❌ VIOLADO

**Archivo:** `src/main.py` → función `bank_analytics()`

**Problema:**
La función `bank_analytics()` tiene **7 responsabilidades diferentes**:
1. Logging de eventos
2. Disambiguación NLP
3. Validación de queries
4. Ejecución de consultas SQL
5. Generación de visualizaciones
6. Manejo de errores
7. Formateo de respuestas

**Evidencia:**
```python
async def bank_analytics(metric_or_query: str, mode: str = "dashboard"):
    logger.info(...)  # 1. Logging
    intent = IntentService.disambiguate(...)  # 2. NLP
    if intent.is_ambiguous: return {...}  # 3. Validación
    async with AsyncSessionLocal() as session:
        payload = await AnalyticsService.get_dashboard_data(...)  # 4. SQL
    plotly_config = VisualizationService.build_plotly_config(...)  # 5. Viz
    return {...}  # 7. Formateo
```

**Impacto:**
- Difícil de testear (necesitas mockear 4+ servicios)
- Difícil de mantener (cambios en una responsabilidad afectan todo)
- Difícil de extender (agregar nuevo modo requiere modificar todo)

---

### 2. **OCP (Open/Closed Principle)** ❌ VIOLADO

**Archivo:** `src/main.py` → función `bank_analytics()`

**Problema:**
El código está **cerrado para extensión**. Para agregar un nuevo tipo de análisis o modo de visualización, debes modificar `bank_analytics()`.

**Evidencia:**
```python
# Hardcoded mode parameter
async def bank_analytics(metric_or_query: str, mode: str = "dashboard"):
    # Logic específica para dashboard/timeline
    plotly_config = VisualizationService.build_plotly_config(...)
```

**Impacto:**
- Agregar "comparison" mode requiere cambiar `bank_analytics()`
- Agregar "heatmap" mode requiere cambiar `bank_analytics()`
- Agregar "forecast" mode requiere cambiar `bank_analytics()`

**Solución propuesta:**
Strategy Pattern para modos de visualización.

---

### 3. **LSP (Liskov Substitution Principle)** ✅ OK

**Status:** No hay jerarquías de clases actualmente, por lo tanto LSP no aplica.

---

### 4. **ISP (Interface Segregation Principle)** ✅ OK

**Status:** No hay interfaces grandes que obliguen a implementar métodos innecesarios.

---

### 5. **DIP (Dependency Inversion Principle)** ❌ VIOLADO

**Archivo:** `src/main.py` → función `bank_analytics()`

**Problema:**
El código de alto nivel (`bank_analytics`) depende **directamente de implementaciones concretas** de bajo nivel.

**Evidencia:**
```python
# Dependencias CONCRETAS (no abstracciones)
from bankadvisor.services.analytics_service import AnalyticsService
from bankadvisor.services.intent_service import IntentService
from bankadvisor.services.visualization_service import VisualizationService
from bankadvisor.db import AsyncSessionLocal

# Uso directo de implementaciones concretas
intent = IntentService.disambiguate(...)
async with AsyncSessionLocal() as session:
    payload = await AnalyticsService.get_dashboard_data(...)
```

**Impacto:**
- Imposible cambiar implementación sin modificar `bank_analytics()`
- Difícil de testear (necesitas instanciar clases reales)
- Acoplamiento fuerte (cambios en servicios rompen `bank_analytics()`)

**Solución propuesta:**
- Crear interfaces abstractas (Protocols en Python)
- Inyección de dependencias

---

## 🎨 Patrones de Diseño Aplicables

### 1. **Strategy Pattern**
**Uso:** Diferentes modos de visualización (dashboard, timeline, comparison)

```python
class VisualizationStrategy(Protocol):
    def build_config(self, data: List[Dict]) -> Dict: ...

class DashboardStrategy:
    def build_config(self, data): return {...}

class TimelineStrategy:
    def build_config(self, data): return {...}
```

### 2. **Factory Pattern**
**Uso:** Crear visualizaciones basadas en el modo

```python
class VisualizationFactory:
    @staticmethod
    def create(mode: str) -> VisualizationStrategy:
        if mode == "dashboard": return DashboardStrategy()
        if mode == "timeline": return TimelineStrategy()
```

### 3. **Command Pattern**
**Uso:** Encapsular queries como objetos

```python
class AnalyticsQuery:
    def __init__(self, metric: str, mode: str):
        self.metric = metric
        self.mode = mode

    def execute(self, session) -> Dict: ...
```

### 4. **Chain of Responsibility**
**Uso:** Pipeline de procesamiento (NLP → Validation → SQL → Viz)

```python
class Handler(Protocol):
    def handle(self, request: Request) -> Response: ...

class NLPHandler(Handler):
    def handle(self, request):
        # Disambiguate
        return next_handler.handle(request)
```

### 5. **Repository Pattern**
**Uso:** Abstraer acceso a datos

```python
class MetricsRepository(Protocol):
    async def get_monthly_kpis(self, metric: str) -> List[MonthlyKPI]: ...

class PostgresMetricsRepository(MetricsRepository):
    async def get_monthly_kpis(self, metric: str):
        async with self.session_factory() as session:
            return await session.execute(...)
```

### 6. **Dependency Injection**
**Uso:** Inyectar servicios en lugar de importarlos directamente

```python
class BankAnalyticsTool:
    def __init__(
        self,
        intent_service: IntentService,
        analytics_service: AnalyticsService,
        viz_factory: VisualizationFactory
    ):
        self.intent = intent_service
        self.analytics = analytics_service
        self.viz_factory = viz_factory

    async def execute(self, query: str, mode: str):
        # Use injected dependencies
```

---

## 🧹 Code Smells Detectados

### 1. **God Function**
`bank_analytics()` hace demasiado (90 líneas, 7 responsabilidades)

### 2. **Primitive Obsession**
Uso excesivo de `Dict[str, Any]` en lugar de dataclasses

```python
# ANTES (primitive)
return {
    "data": payload["data"],
    "metadata": payload["metadata"],
    "plotly_config": plotly_config
}

# DESPUÉS (dataclass)
@dataclass
class AnalyticsResponse:
    data: AnalyticsData
    metadata: Metadata
    plotly_config: PlotlyConfig
```

### 3. **Magic Strings**
```python
# ANTES
if intent.is_ambiguous:
    return {"error": "ambiguous_query"}

# DESPUÉS
class ErrorType(Enum):
    AMBIGUOUS_QUERY = "ambiguous_query"
    VALIDATION_FAILED = "validation_failed"
```

### 4. **Implicit Dependencies**
```python
# ANTES
async def bank_analytics(...):
    async with AsyncSessionLocal() as session:  # ¿De dónde viene?
        ...

# DESPUÉS
async def bank_analytics(
    query: str,
    mode: str,
    session_factory: Callable[[], AsyncSession]  # Explícito
):
    async with session_factory() as session:
        ...
```

---

## 📊 Métricas de Complejidad

| Métrica | Antes | Después (Goal) |
|---------|-------|----------------|
| **Cyclomatic Complexity** | 8 | < 4 |
| **Lines of Code** | 90 | < 30 por función |
| **Dependencies** | 4 concretas | 3 abstracciones |
| **Test Coverage** | 0% | > 80% |

---

## 🎯 Plan de Refactorización

### Fase 1: Extraer Responsabilidades (SRP)
1. Crear `BankAnalyticsOrchestrator` (coordina el flujo)
2. Crear `QueryValidator` (valida queries)
3. Crear `ResponseFormatter` (formatea respuestas)

### Fase 2: Inyección de Dependencias (DIP)
1. Crear `protocols.py` con interfaces abstractas
2. Modificar servicios para implementar protocols
3. Usar dependency injection en `BankAnalyticsOrchestrator`

### Fase 3: Patrones de Diseño (OCP)
1. Implementar Strategy Pattern para visualizaciones
2. Implementar Factory Pattern para crear strategies
3. Implementar Chain of Responsibility para pipeline

### Fase 4: Limpieza
1. Eliminar código duplicado
2. Reemplazar primitives con dataclasses
3. Agregar type hints completos

---

## 🚀 Beneficios Esperados

1. **Testability:** Cada componente es testeable independientemente
2. **Maintainability:** Cambios aislados en cada responsabilidad
3. **Extensibility:** Agregar modos sin modificar código existente
4. **Readability:** Código auto-documentado con nombres claros
5. **Reusability:** Componentes reutilizables en otros contextos

---

**Status:** Análisis completado
**Next Step:** Implementar refactorización
