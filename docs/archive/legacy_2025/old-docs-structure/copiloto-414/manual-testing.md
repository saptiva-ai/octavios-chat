# Copiloto 414 · Pruebas Manuales

Esta guía documenta el smoke test manual recomendado antes de entregas a Capital 414. Cubre la ingesta de archivos, la ejecución de auditorías y la verificación de que los hallazgos se reutilizan en el chat.

> Ejecutar en un entorno local levantado con `make dev` o en staging con credenciales de demo. Asegúrate de exportar `NEXT_PUBLIC_API_URL` sin sufijo `/api` si construyes el frontend de manera manual.

---

## 1. Preparación

1. Levantar stack completo:
   ```bash
   make setup   # solo la primera vez
   make dev     # inicia web, api, mongodb, redis, minio
   ```
   > Los comandos posteriores asumen el `COMPOSE_PROJECT_NAME` por defecto (`octavios`). Sustituye el prefijo si tu entorno usa otro nombre.
2. Crear usuario demo (si no existe):
   ```bash
   make create-demo-user
   ```
3. Abrir http://localhost:3000, iniciar sesión con `demo / Demo1234`.
4. Conservar panel de minio opcional (`http://localhost:9001`) para monitorear objetos (`documents/`, `audit-reports/`).

**Archivos de prueba** (`tests/data/client-project/`):

| Archivo | Escenario |
|---------|-----------|
| `ClientProject_presentacion.pdf` | Documento completo con disclaimers correctos |
| `ClientProject_ProcesoValoracion.pdf` | Contenido con cifras y tablas |
| `ClientProject_usoIA.pdf` | Material con gráficos (prueba de logo y color) |

---

## 2. Ingesta de archivos (Files V1)

1. Desde el chat, usar **Agregar archivos** y cargar `ClientProject_presentacion.pdf`.
2. Confirmar en UI que aparecen los estados `Subiendo → Procesando → Listo` en menos de 90s.
3. Verificar SSE en consola:
   ```bash
   docker logs -f octavios-api | grep FileEventPayload
   ```
4. Validar en Mongo:
   ```bash
   docker exec -it octavios-mongodb mongosh copilotos \
     --eval 'db.documents.find().sort({created_at:-1}).limit(1).pretty()'
   ```
   - `status` debe ser `"ready"`.
   - `minio_key` debe apuntar a `documents/<user>/<chat>/<file>.pdf`.
5. Revisar que el binario exista en MinIO (`mc ls local/documents/...` o panel web).

---

## 3. Auditoría Copiloto 414

1. Con el archivo en estado Ready, activar el toggle **Auditar con Copiloto 414** y enviar un mensaje “Auditar este documento”.
2. Esperar la tarjeta de resultados (`MessageAuditCard`). Validar:
   - `summary.total_findings` mostrado.
   - Botones habilitados (`Ver reporte completo`, `Reintentar`).
   - Etiqueta de política detectada (`414-std` esperado).
3. Confirmar persistencia en Mongo:
   ```bash
   docker exec -it client-project-chat-mongodb mongosh copilotos \
     --eval 'db.validation_reports.find().sort({created_at:-1}).limit(1).pretty()'
   ```
   - `policy_id`, `summary.findings_by_severity`, `document_id` deben estar presentes.
4. Inspeccionar logs para policy detector:
   ```bash
   docker logs -f octavios-api | grep "Policy resolved"
   ```
5. Validar que exista objeto en MinIO en `audit-reports/` cuando se exporta (opcional: usar acción “Descargar reporte”).

---

## 4. Contexto en el Chat

1. Preguntar en el hilo: “¿Cuáles son los hallazgos críticos del documento?”
2. Confirmar que la respuesta del asistente incluye referencias a los findings (ver logs `Validation context formatted`).
3. Validar en Redis que el cache exista mientras dura la sesión:
   ```bash
   docker exec -it octavios-redis redis-cli GET doc:text:<document_id>
   ```
4. Limpiar archivos y repetir con `ClientProject_ProcesoValoracion.pdf` para verificar detección de formato numérico.

---

## 5. Casos negativos

| Caso | Procedimiento | Resultado esperado |
|------|---------------|--------------------|
| Tamaño excedido | Subir un archivo > `MAX_FILE_SIZE_MB` | Toast de error, log `UPLOAD_TOO_LARGE`, status 413 |
| Tipo no soportado | Subir `.zip` | Error 415 `Unsupported file type` |
| Documento sin disclaimers | Usar PDF sin footer legal | Hallazgo crítico `Disclaimer ausente` |
| Política baja confianza | Documento sin indicadores | Policy fallback a `auto` + prompt aclaratorio en chat |

---

## 6. Limpieza

```bash
make stop-all
make clean      # elimina contenedores y volúmenes temporales
```

> Nota: Los documentos generados quedan en MinIO. Ejecutar `mc rm --recursive --force local/documents/<user>/` si se requiere limpieza completa.
