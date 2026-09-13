# Backend de OMEGA Creative

## Iniciar

Desde esta carpeta ejecuta:

```powershell
py server.py
```

Luego abre:

`http://127.0.0.1:8000/omega.creative.html`

El formulario de contacto acepta imágenes y documentos y los envía a `POST /api/contact`. Cada consulta queda guardada en `data/submissions/` con un archivo `submission.json` y sus adjuntos.

Las opiniones se publican desde `contacto.html` mediante `POST /api/review` y se guardan en `data/reviews.json`.

## Portafolio de administración

Define un token antes de iniciar el servidor:

```powershell
$env:OMEGA_ADMIN_TOKEN = "elige-un-token-seguro"
py server.py
```

En `proceso.html`, el administrador introduce ese token y puede subir imágenes al portafolio. Los archivos se guardan en `data/portfolio/` y se muestran automáticamente en la página.

## Cuentas

Las cuentas se guardan en `data/omega.db`. Para habilitar el registro de administradores, configura un código separado:

```powershell
$env:OMEGA_ADMIN_REGISTRATION_CODE = "codigo-de-invitacion"
py server.py
```

Los clientes pueden registrarse desde `cuenta.html`. Las contraseñas se almacenan con PBKDF2 y las sesiones duran 7 días.

El límite actual es de 25 MB por envío. Para publicar el sitio, cambia `127.0.0.1` por la configuración del servidor y añade autenticación, HTTPS y una política de retención para los archivos recibidos.
