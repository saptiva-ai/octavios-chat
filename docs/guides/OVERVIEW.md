# 📚 Copilotos Bridge Documentation Hub

Punto de partida para localizar guías, runbooks y reportes del proyecto.

---

## 🚀 Primeros Pasos
- [Guía de Inicio Rápido](GETTING_STARTED.md)
- [Quick Start para el equipo](guides/QUICK_START.md)
- [Referencia de credenciales para onboarding](guides/CREDENTIALS.md)

---

## 🛠️ Operaciones & Runbooks
- [Playbook de despliegue a producción](operations/deployment.md)
- [Gestión y rotación de credenciales](operations/credentials.md)
- Respaldo y recuperación: [backup setup](operations/backup-setup.md) · [disaster recovery](operations/disaster-recovery.md)
- Optimización diaria: [recursos](operations/resource-optimization.md) · [patterns SSH](operations/ssh-environment-patterns.md) · [troubleshooting](operations/troubleshooting.md)
- Incidentes y post-mortems: [`operations/incidents/`](operations/incidents/)

---

## 🔐 Seguridad
- [Security audit report](security/security-audit-report.md)
- [Security alert playbook](security/security-alert.md)
- Ver también: [gestión de credenciales](operations/credentials.md)

---

## 🔎 Saptiva & Text Extraction
- Documentación completa de investigación y soporte: [`saptiva/`](saptiva/)
- Abstracción de extractores, inventario y roadmap: [`extraction/`](extraction/)
- OCR prompts, validaciones y mejoras: [`ocr/`](ocr/)

---

## 🧱 Arquitectura & Producto
- Copiloto 414 (arquitectura + pruebas): [`copiloto-414/`](copiloto-414/)
- Diagramas LLM y flujos internos: [`arquitectura/`](arquitectura/)
- Integraciones Web y chat: [`web/`](web/)
- Document review & Files V1: [`document-review/`](document-review/)
- Tech debt & mejoras: [`arquitectura/TECH_DEBT.md`](arquitectura/TECH_DEBT.md)

---

## ✅ Calidad, Testing & Evidencias
- Estado de cobertura: [Test Coverage Dashboard](testing/test-coverage.md)
- Reportes y planes de pruebas: [`testing/`](testing/)
- Evidencias reproducibles: [`evidencias/`](evidencias/)
- Ver también: [`bugfixes/`](bugfixes/) para cambios y post-mortems específicos.

---

## 🔄 CI/CD y Entrega Continua
- Pipelines empresariales y automatización: [`ci-cd/`](ci-cd/)
- Playbook de scripts de despliegue: [`deployment/`](deployment/) y [`../scripts/README-DEPLOY.md`](../scripts/README-DEPLOY.md)
- Configuración de entornos: [`setup/`](setup/)

---

## 📦 Archivo Histórico
- Documentos legacy agrupados en [`archive/`](archive/)
- Referencias destacadas: [legacy deployment](archive/legacy-deployment/) · [legacy credentials](archive/legacy-credentials/) · [legacy testing](archive/legacy-testing/)

---

## 📌 Otros Recursos
- Registro de cambios principal: [CHANGELOG.md](CHANGELOG.md)
- Makefile con comandos clave: [`../Makefile`](../Makefile) (`make help`)
