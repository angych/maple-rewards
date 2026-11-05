# Maple Rewards V5 — preparado para despliegue, NO publicado

Esta versión incluye la interfaz y el backend de V4, Dockerfile, configuración de entorno de ejemplo, verificación de salud `/healthz`, validación de origen para solicitudes que modifican datos y cálculo de cumpleaños en la zona horaria de Buenos Aires.

## Prueba local (PC)
1. Instalá Python 3.11 o superior.
2. `python -m pip install -r requirements.txt`
3. `python create_admin.py` (crear credenciales ficticias de prueba)
4. `python -m uvicorn server:app --host 127.0.0.1 --port 8000`
5. Abrí `http://127.0.0.1:8000`.

## Preparación de hosting
- Necesitás un hosting que ejecute contenedores Docker y **almacenamiento persistente**. La base SQLite se guarda en `MAPLE_DB`; en Docker el valor por defecto es `/data/maple.sqlite3` y **/data debe ser un volumen persistente**. Sin volumen se perderán las cuentas al reiniciar o redesplegar.
- Configurá un dominio HTTPS y `MAPLE_PUBLIC_ORIGIN=https://tu-dominio` sin barra final.
- El contenedor usa cookies Secure; la aplicación publicada necesita HTTPS.
- Creá el primer administrador ejecutando `python create_admin.py` dentro del contenedor con acceso al mismo volumen, no en una instancia con base de datos distinta.
- Hacé backups cifrados periódicos del volumen y probá la restauración.

## IMPORTANTE: no apto para clientes reales todavía
No está publicado ni conectado a Maple Tickets. Quedan pendientes controles completos de CSRF, límites de intentos de login, verificación y recuperación de correo, gestión segura de secretos, políticas de privacidad y retención, auditoría, supervisión, copias de seguridad probadas, revisión de seguridad y pruebas end-to-end en hosting. El QR identifica a un cliente pero no autoriza por sí solo un cobro ni canje. El panel manual requiere administrador; la integración POS exige autenticación servidor a servidor y validación del pago real. No ingreses información personal real en esta etapa.

## Reglas
10 sellos por café gratis; 1 sello por café pagado elegible; bienvenida +1 una sola vez; sin vencimiento; cumpleaños gratis una vez por año en el día; cafés gratis no generan sellos. La venta manual del panel permite registrar cantidades para pruebas, pero aún no valida productos ni comprobantes del POS.
