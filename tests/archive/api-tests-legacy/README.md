# Legacy Test Suite

Este directorio contiene tests heredados que han sido movidos fuera de la suite principal de pruebas para mantener `make test-api` ejecutable sin bloqueos.

## 📂 Estructura

```
tests_legacy/
├── debug/          # Scripts de prueba para debugging manual (Aletheia client, etc.)
├── e2e/            # Tests E2E legacy pendientes de migración a Playwright/HTTPx
├── integration/    # Tests de integración con dependencias externas
└── unit/           # Tests unitarios con imports obsoletos o dependencias faltantes
```

## ⚠️ Estado

**Estos tests NO se ejecutan en CI** y están marcados en `pytest.ini` como `norecursedirs`.

### ¿Por qué están aquí?

1. **Dependencias obsoletas**: Algunos usan imports que ya no existen o han sido refactorizados
2. **Requieren setup manual**: Tests de integración que necesitan credenciales/servicios externos
3. **Pendientes de modernización**: E2E tests que deben migrarse a Playwright o HTTPx estable

## 🔄 Próximos Pasos

### Para Migrar Tests Legacy:

1. **Identificar el problema**: ¿Por qué fallan?
   - Imports obsoletos → Actualizar a nuevas rutas
   - Dependencias faltantes → Instalar o mockear
   - Lógica obsoleta → Reescribir con APIs actuales

2. **Actualizar el test**:
   - Refactorizar para usar imports modernos
   - Agregar mocks apropiados para dependencias externas
   - Asegurar que pase con `pytest tests_legacy/unit/test_xxx.py -v`

3. **Mover de vuelta a la suite principal**:
   ```bash
   git mv tests_legacy/unit/test_xxx.py tests/unit/
   ```

4. **Verificar en CI**:
   ```bash
   make test-api  # Debe pasar sin errores
   ```

### Para E2E Tests:

Considerar migración a:
- **Playwright** (para tests de UI completos)
- **HTTPx** con TestClient (para tests de API sin navegador)

## 🏃 Ejecución Manual

Si necesitas ejecutar estos tests localmente (para debugging):

```bash
# Ejecutar un test específico
pytest tests_legacy/debug/test_aletheia_client.py -v

# Ejecutar todos los tests legacy (algunos fallarán)
pytest tests_legacy/ -v

# Ejecutar solo tests marcados con @pytest.mark.legacy
pytest -m legacy -v
```

## 📊 Métricas

**Tests movidos a legacy**: 12 archivos
- Debug: 2
- E2E: 3
- Integration: 2
- Unit: 5

**Razón principal**: Module-level `pytest.skip()` bloqueaba la suite completa

---

**Última actualización**: 2025-10-20
**Responsable**: Equipo Saptiva AI + Claude Code
