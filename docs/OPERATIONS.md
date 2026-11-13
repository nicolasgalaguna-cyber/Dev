# Operación y despliegue

## Configuración

| Variable | Valor / uso |
| --- | --- |
| RADIO_TOKEN | Obligatoria, mínimo 16 caracteres; recomienda 32 aleatorios |
| RADIO_DATA | Directorio persistente; data local, /data en Docker |
| HOST / PORT | 127.0.0.1 / 8080 local; 0.0.0.0 dentro del contenedor |
| STATION_TIMEZONE | America/Bogota; nombre IANA usado por la parrilla |
| COOKIE_SECURE | 1 bajo HTTPS; 0 para localhost HTTP |
| OPENAI_API_KEY | Opcional, secreto del servidor |
| OPENAI_MODEL | gpt-6-astra; configurable según acceso API |
| ICECAST_SOURCE_PASSWORD | Clave distinta para el emisor |
| ICECAST_ADMIN_PASSWORD | Clave distinta para administrador |

El reloj mostrado en la UI está fijado a Bogotá; si cambias la zona del servidor, cambia también la etiqueta y formateador en public/app.js. El servidor debe mantener su hora sincronizada.

Genera claves con `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` y colócalas en `.env`. No las subas al repositorio. En local sin Docker, exporta variables en tu shell; el servidor no lee .env automáticamente.

## HTTPS y proxy

En un servidor con Docker, deja la consola y Icecast publicados en 127.0.0.1. Instala un proxy TLS y limita acceso al estudio mediante VPN o autenticación adicional. Configura límite de carga de 80 MB, tiempos de importación de 120 s, y desactiva buffering para /stream.wav. Ejemplo orientativo de rutas Nginx dentro de tu bloque TLS ya configurado:

```nginx
client_max_body_size 80m;
location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host $host;
    proxy_read_timeout 120s;
}
location = /stream.wav {
    proxy_pass http://127.0.0.1:8080;
    proxy_buffering off;
    proxy_read_timeout 3600s;
}
```

Para la audiencia usa un subdominio público dirigido a Icecast, con /radio.mp3 sin buffering. Protege /admin y no expongas sus credenciales. Las conexiones de audio son persistentes; configura límites y monitoreo del proxy. La configuración TLS completa, DNS y certificados dependen de tu infraestructura y no están desplegados por este repositorio.

## Inicio y recuperación

1. `docker compose up --build -d`.
2. Revisa `docker compose ps` y `docker compose logs radio`.
3. Carga demo o tu audio, inicia sesión y pulsa Iniciar emisión.
4. Activa el perfil broadcast si usarás Icecast.
5. Comprueba desde otro cliente que /radio.mp3 emite y que el servidor sigue sonando al cerrar la consola.
6. Prueba la pérdida de conexión del micrófono y el retorno de música antes de emitir en vivo.

La política restart reinicia procesos, pero no reanuda automáticamente el transporte al reiniciar la aplicación. /health comprueba que el hilo de audio vive, no que haya música ni audiencia. Revisa errores de la consola; un archivo inválido se omite en la rotación. Si se pierde el puente Icecast, reintenta cada 5 segundos.

## Backup

Detén el servicio de radio antes de copiar, para conservar consistentes SQLite, WAL y archivos. El perfil bridge debe estar detenido también durante mantenimiento.

```sh
docker compose --profile broadcast stop
mkdir -p backups
docker compose run --rm --no-deps -v "$PWD/backups:/backup" radio \
    python -c "import shutil; shutil.make_archive('/backup/station', 'gztar', '/data')"
docker compose --profile broadcast up -d
```

La carpeta backups debe permitir escritura al uid 10001 del contenedor. Conserva .env por separado en un almacén seguro. Para restaurar, detén servicios y extrae la copia en el volumen /data usando herramientas de administración de tu host; conserva propietario uid 10001 y no sobrescribas una biblioteca activa. Arranca, comprueba biblioteca/parrilla y vuelve a iniciar la emisión manualmente.

En local, detén Python y copia `data/` completo. Nunca distribuyas ese directorio con el código: puede contener audio con licencia y datos editoriales privados.

## Prueba de aceptación en el servidor final

- Importar WAV y MP3, oír dos transiciones completas, saltar y confirmar historial.
- Programar un bloque cercano y comprobar cambio de lista al preparar pista.
- Abrir dos sesiones distintas y comprobar exclusividad de micro.
- Desconectar el locutor: música vuelve tras 3 segundos.
- Escuchar MP3 en VLC y un teléfono por al menos 30 minutos.
- Reiniciar bridge, radio e Icecast; confirmar el procedimiento de recuperación.
- Ejecutar consulta IA con clave real, abrir sus fuentes y registrar revisión manual.

Estos pasos requieren hardware, Docker y cuenta API del operador y no se declaran aprobados por las pruebas locales.
