# Seguridad

Para informar un fallo, usa la pestaña Security del repositorio y la opción de reporte privado si está habilitada. Si no está disponible, contacta al propietario por un canal privado que ya conozcas. No publiques claves, grabaciones privadas ni pruebas de explotación en issues.

Este MVP usa una clave compartida de estudio y sesiones de 12 horas, sin roles por usuario. Configura una clave aleatoria, limita el acceso al estudio a tu equipo o VPN, y termina TLS en un proxy. Activa COOKIE_SECURE=1 con HTTPS. La salida /stream.wav es pública intencionalmente; los medios y comandos exigen sesión.

No expongas el servidor HTTP de desarrollo directamente a Internet. El parser HTTP, las cargas y el número de conexiones deben quedar limitados también en tu proxy. El límite interno de carga es de 80 MB y los monitores directos son como máximo 20; Icecast distribuye a la audiencia.

FFmpeg procesa archivos aportados por operadores de confianza; mantén su imagen actualizada. No se descargan URL de audio arbitrarias ni fuentes editoriales desde el servidor. La IA recibe solamente título y artista; su salida se muestra como texto, nunca HTML. Aun con fuentes, necesita contraste humano.

Los secretos del puente Icecast aparecen en los argumentos del proceso FFmpeg dentro de su contenedor. No compartas sus listados de procesos ni uses ese contenedor con usuarios no confiables.
