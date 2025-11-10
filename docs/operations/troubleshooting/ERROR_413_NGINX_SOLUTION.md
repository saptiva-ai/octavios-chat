# 🚨 Solución Error 413 (Content Too Large) - Nginx

**Síntoma:** Al intentar subir HPE.pdf (2.3MB) en `https://copilotos.saptiva.com`, el navegador muestra:

```
POST https://copilotos.saptiva.com/api/files/upload 413 (Content Too Large)
```

---

## 🔍 Causa Raíz

`★ Insight ─────────────────────────────────────`
**Error 413 es de Nginx, NO del backend:**
- El archivo **nunca llega al backend** - Nginx lo rechaza inmediatamente
- Ocurre cuando `Content-Length` del request > `client_max_body_size`
- Default de nginx: **1MB** (muy bajo para PDFs)
`─────────────────────────────────────────────────`

### Arquitectura del Problema

```
Internet → [Nginx Sistema (/etc/nginx/)] → [Nginx Docker] → Backend
           ↑ client_max_body_size: 1M
           ✗ RECHAZA archivos > 1MB
```

El dominio `copilotos.saptiva.com` sugiere que hay un **Nginx del sistema** (instalado con APT/YUM) que hace de proxy reverso ANTES del stack de Docker.

---

## ⚡ Solución Rápida (3 minutos)

### Paso 1: Ejecutar Script de Diagnóstico

Conéctate al servidor:

```bash
ssh jf@34.42.214.246

cd /home/jf/copilotos-bridge

# Diagnosticar dónde está el problema
bash scripts/diagnose-nginx-413.sh
```

**Salida esperada:**
```
✗ client_max_body_size NO configurado en /etc/nginx/sites-enabled/copilotos
  (default: 1M)
↳ ESTE ES PROBABLEMENTE EL PROBLEMA
```

### Paso 2: Aplicar Fix Automático

```bash
# Con permisos de root
sudo bash scripts/fix-nginx-413.sh

# O modo dry-run primero (para ver qué hará):
sudo bash scripts/fix-nginx-413.sh --dry-run
```

**Lo que hace el script:**
1. ✅ Crea backup de la configuración
2. ✅ Agrega/actualiza `client_max_body_size 50M;`
3. ✅ Valida sintaxis con `nginx -t`
4. ✅ Recarga nginx automáticamente

### Paso 3: Verificar

Desde el navegador, intenta subir HPE.pdf de nuevo:
- ✅ **Debe funcionar** sin error 413
- ❌ Si persiste, ejecuta `bash scripts/diagnose-nginx-413.sh` y revisa la sección "Recomendaciones"

---

## 🛠️ Solución Manual (Si prefieres hacerlo a mano)

### Opción A: Nginx del Sistema

```bash
# 1. Identificar archivo de configuración
sudo find /etc/nginx -name "*copilotos*" -o -name "*saptiva*"

# O usar grep
sudo grep -rl "copilotos.saptiva.com" /etc/nginx/

# 2. Editar el archivo encontrado
sudo nano /etc/nginx/sites-enabled/copilotos

# 3. Agregar dentro del bloque 'server {}':
server {
    listen 80;
    server_name copilotos.saptiva.com;

    client_max_body_size 50M;  # ← AGREGAR ESTA LÍNEA

    location / {
        proxy_pass http://localhost:3000;
        # ... resto de configuración
    }
}

# 4. Validar sintaxis
sudo nginx -t

# 5. Recargar nginx
sudo systemctl reload nginx
```

### Opción B: Nginx de Docker

Si el script detecta que el problema está en Docker:

```bash
# 1. Verificar configuración actual
docker exec copilotos-nginx cat /etc/nginx/nginx.conf | grep client_max_body_size

# 2. Si falta, editar docker-compose o reconstruir imagen
# Ver: infra/nginx/nginx.conf línea 12
#      client_max_body_size 50M;

# 3. Recrear contenedor
docker-compose -f infra/docker-compose.prod.yml up -d nginx --force-recreate
```

---

## 🧪 Verificación Multi-capa

Después de aplicar el fix, verifica TODAS las capas:

```bash
# En el servidor
cd /home/jf/copilotos-bridge

# 1. Nginx del sistema
sudo grep -r "client_max_body_size" /etc/nginx/
# Debe mostrar: client_max_body_size 50M;

# 2. Nginx de Docker (si aplica)
docker exec copilotos-nginx grep "client_max_body_size" /etc/nginx/nginx.conf
# Debe mostrar: client_max_body_size 50M;

# 3. Backend
grep "MAX_FILE_SIZE" envs/.env.prod
# Debe mostrar: MAX_FILE_SIZE=52428800

# 4. Frontend (requiere rebuild de imagen)
# Ver: docs/troubleshooting/ENV_SERVER_AUDIT_AND_FIX.md
```

---

## 📊 Matriz de Límites (Debe ser consistente)

| Capa | Variable/Config | Valor Correcto | Ubicación |
|------|-----------------|----------------|-----------|
| **Nginx Sistema** | `client_max_body_size` | `50M` | `/etc/nginx/sites-enabled/copilotos` |
| **Nginx Docker** | `client_max_body_size` | `50M` | `infra/nginx/nginx.conf:12` |
| **Backend** | `MAX_FILE_SIZE` | `52428800` | `envs/.env.prod` |
| **Frontend (Build)** | `NEXT_PUBLIC_MAX_FILE_SIZE_MB` | `50` | `envs/.env.prod` + Dockerfile ARG |
| **Frontend (Runtime)** | `NEXT_PUBLIC_MAX_FILE_SIZE_MB` | `50` | `docker-compose.prod.yml:168` |

---

## 🚫 Errores Comunes

### Error 1: "Permission denied" al ejecutar fix

```bash
# INCORRECTO
bash scripts/fix-nginx-413.sh

# CORRECTO (requiere sudo)
sudo bash scripts/fix-nginx-413.sh
```

### Error 2: "nginx: configuration file /etc/nginx/nginx.conf test failed"

```bash
# Ver detalles del error
sudo nginx -t

# Restaurar backup si rompiste algo
sudo cp /etc/nginx/sites-enabled/copilotos.backup-YYYYMMDD /etc/nginx/sites-enabled/copilotos
sudo systemctl reload nginx
```

### Error 3: Persiste después del fix

Posibles causas:
1. **Caché del navegador:** Fuerza refresh (Ctrl+Shift+R)
2. **Múltiples nginx:** Verifica que actualizaste el correcto con `diagnose-nginx-413.sh`
3. **CDN/Proxy:** Si usas Cloudflare u otro CDN, también tiene límites de tamaño

---

## 🔧 Troubleshooting Avanzado

### Ver logs de nginx en tiempo real

```bash
# Sistema
sudo tail -f /var/log/nginx/error.log

# Docker
docker logs -f copilotos-nginx
```

### Probar con curl (bypassing browser cache)

```bash
# Crear archivo de prueba de 2MB
dd if=/dev/zero of=/tmp/test-2mb.bin bs=1M count=2

# Test directo
curl -v -X POST -F "file=@/tmp/test-2mb.bin" https://copilotos.saptiva.com/api/files/upload

# Si retorna 413: Nginx rechaza
# Si retorna 401/403: Nginx acepta (falta auth, pero tamaño OK)
```

### Verificar arquitectura de red

```bash
# Ver qué procesos escuchan en puertos HTTP
sudo ss -tlnp | grep ':80\|:443'

# Ver proxy_pass en configuración
sudo grep -r "proxy_pass" /etc/nginx/
```

---

## 📚 Referencias

- **Script diagnóstico:** [`scripts/diagnose-nginx-413.sh`](../../scripts/diagnose-nginx-413.sh)
- **Script fix:** [`scripts/fix-nginx-413.sh`](../../scripts/fix-nginx-413.sh)
- **Auditoría completa:** [`ENV_SERVER_AUDIT_AND_FIX.md`](./ENV_SERVER_AUDIT_AND_FIX.md)
- **Nginx oficial:** [client_max_body_size](http://nginx.org/en/docs/http/ngx_http_core_module.html#client_max_body_size)

---

## ✅ Checklist Post-Fix

```bash
☐ Script de diagnóstico ejecutado
☐ client_max_body_size actualizado a 50M
☐ nginx -t pasa sin errores
☐ nginx recargado (systemctl reload nginx)
☐ Upload de HPE.pdf funciona sin error 413
☐ DevTools no muestra errores en Network tab
☐ Backend logs muestran archivo recibido correctamente
```

---

**Última actualización:** 2025-10-21 02:45 UTC-6
**Estado:** ✅ Scripts listos para ejecutar
**Tiempo estimado de fix:** 3-5 minutos
