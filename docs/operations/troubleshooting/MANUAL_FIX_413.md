# 🔧 Fix Manual del Error 413 (Sin Scripts)

Si prefieres hacer los cambios manualmente sin scripts automáticos, sigue esta guía.

---

## Paso 1: Identificar el Archivo de Configuración

```bash
# Buscar configuración de copilotos.saptiva.com
sudo find /etc/nginx -type f -name "*.conf" -o -name "default" | xargs grep -l "copilotos\|saptiva" 2>/dev/null

# O más simple:
sudo grep -rl "copilotos.saptiva.com" /etc/nginx/
```

**Ubicaciones comunes:**
- Debian/Ubuntu: `/etc/nginx/sites-enabled/copilotos`
- CentOS/RHEL: `/etc/nginx/conf.d/copilotos.conf`
- Default: `/etc/nginx/sites-enabled/default`

---

## Paso 2: Ver Configuración Actual

```bash
# Reemplaza ARCHIVO con el resultado del paso anterior
sudo cat /etc/nginx/sites-enabled/copilotos
```

**Busca** esta línea:
```nginx
client_max_body_size 1M;  # O cualquier valor < 50M
```

**Si NO existe**, la agregarás. **Si existe**, la editarás.

---

## Paso 3: Editar el Archivo

```bash
# Crear backup primero
sudo cp /etc/nginx/sites-enabled/copilotos /etc/nginx/sites-enabled/copilotos.backup

# Editar con nano (más fácil)
sudo nano /etc/nginx/sites-enabled/copilotos

# O con vim
sudo vim /etc/nginx/sites-enabled/copilotos
```

---

## Paso 4: Agregar/Modificar la Línea

### **Caso A: El archivo tiene un bloque `server {}`**

```nginx
server {
    listen 80;
    server_name copilotos.saptiva.com;

    # ← AGREGAR AQUÍ (después de server_name)
    client_max_body_size 50M;

    location / {
        proxy_pass http://localhost:3000;
        ...
    }

    location /api {
        proxy_pass http://localhost:8001;
        ...
    }
}
```

### **Caso B: El archivo tiene múltiples `server {}`**

Agrégalo en **TODOS** los bloques server (especialmente en el de puerto 443 si existe):

```nginx
# HTTP (puerto 80)
server {
    listen 80;
    server_name copilotos.saptiva.com;
    client_max_body_size 50M;  # ← AQUÍ
    ...
}

# HTTPS (puerto 443)
server {
    listen 443 ssl;
    server_name copilotos.saptiva.com;
    client_max_body_size 50M;  # ← Y AQUÍ
    ...
}
```

### **Caso C: Si existe pero con valor menor**

```nginx
# ANTES:
client_max_body_size 1M;

# DESPUÉS:
client_max_body_size 50M;
```

---

## Paso 5: Guardar y Salir

### **En nano:**
1. `Ctrl + O` (guardar)
2. `Enter` (confirmar nombre de archivo)
3. `Ctrl + X` (salir)

### **En vim:**
1. Presiona `Esc`
2. Escribe `:wq`
3. Presiona `Enter`

---

## Paso 6: Validar Sintaxis

```bash
# Verificar que no rompiste nada
sudo nginx -t
```

**Salida esperada:**
```
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
```

**Si hay error:**
```bash
# Restaurar backup
sudo cp /etc/nginx/sites-enabled/copilotos.backup /etc/nginx/sites-enabled/copilotos

# Ver el error específico
sudo nginx -t
```

---

## Paso 7: Recargar Nginx

```bash
# Opción 1 (recomendada, no interrumpe conexiones)
sudo systemctl reload nginx

# Opción 2 (si systemctl no funciona)
sudo service nginx reload

# Opción 3 (último recurso, reinicia completamente)
sudo systemctl restart nginx
```

**Verificar que sigue corriendo:**
```bash
sudo systemctl status nginx
```

---

## Paso 8: Verificar el Cambio

```bash
# Ver la configuración aplicada
sudo nginx -T | grep -A 2 "client_max_body_size"

# Debe mostrar:
# client_max_body_size 50M;
```

---

## Paso 9: Probar Upload

### **Desde el navegador:**
1. Ir a `https://copilotos.saptiva.com`
2. Subir `HPE.pdf` (2.3MB)
3. Abrir DevTools → Network tab
4. Verificar que `POST /api/files/upload` retorne **200** (no 413)

### **Con curl (alternativo):**
```bash
# Crear archivo de prueba de 2MB
dd if=/dev/zero of=/tmp/test-2mb.bin bs=1M count=2

# Test
curl -v -X POST -F "file=@/tmp/test-2mb.bin" \
  https://copilotos.saptiva.com/api/files/upload

# Si retorna 413: El cambio no se aplicó
# Si retorna 401/403: ✓ Archivo aceptado (falta auth, pero tamaño OK)
# Si retorna 200: ✓ Perfecto
```

---

## 🚨 Troubleshooting

### **Problema: "Permission denied" al editar**

```bash
# Asegúrate de usar sudo
sudo nano /etc/nginx/sites-enabled/copilotos
```

### **Problema: "nginx: configuration file test failed"**

```bash
# Ver línea exacta del error
sudo nginx -t

# Restaurar backup
sudo cp /etc/nginx/sites-enabled/copilotos.backup /etc/nginx/sites-enabled/copilotos
sudo systemctl reload nginx
```

### **Problema: Cambio no se aplica**

```bash
# 1. Verificar que editaste el archivo correcto
sudo grep -rl "copilotos.saptiva.com" /etc/nginx/

# 2. Verificar que nginx recargó
sudo systemctl status nginx

# 3. Ver logs de errores
sudo tail -f /var/log/nginx/error.log
```

### **Problema: Hay múltiples archivos de nginx**

```bash
# Ver TODOS los archivos que mencionan "client_max_body_size"
sudo grep -r "client_max_body_size" /etc/nginx/

# Actualiza el que tiene menor valor
```

---

## ✅ Checklist

```
☐ Backup creado
☐ Archivo editado con client_max_body_size 50M;
☐ sudo nginx -t pasa sin errores
☐ sudo systemctl reload nginx ejecutado
☐ systemctl status nginx muestra "active (running)"
☐ Upload de HPE.pdf funciona sin error 413
```

---

## 🔙 Rollback (Si algo sale mal)

```bash
# Restaurar configuración anterior
sudo cp /etc/nginx/sites-enabled/copilotos.backup /etc/nginx/sites-enabled/copilotos

# Recargar
sudo systemctl reload nginx

# Verificar
sudo systemctl status nginx
```

---

**Tiempo estimado:** 5-7 minutos
**Requiere:** Acceso sudo al servidor
