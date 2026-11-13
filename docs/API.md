# API v1

Base en el mismo origen. JSON UTF-8. Login devuelve cookie HttpOnly. Para todas las demás mutaciones enviar cookie de sesión y `X-Radio-Request: 1`. No hay CORS. Respuestas de error: `{ "error": "descripción" }`; 400 entrada inválida, 401 sin sesión, 429 límite, 502 fallo de servicio.

| Método / ruta | Entrada | Resultado |
| --- | --- | --- |
| GET /health | Pública | Hilo de audio activo |
| POST /api/login | token | Cookie, sesión de 12 h |
| POST /api/logout | {} | Revoca sesión y micro propio |
| GET /api/state | Sesión | station, audio, capabilities |
| POST /api/upload | Binario, Content-Length, X-Title y X-Artist codificados con encodeURIComponent; X-Kind music/jingle | Pista convertida a WAV; 201 |
| GET /media/{track_id} | Sesión, Range opcional | WAV para cue; 200/206 |
| GET /stream.wav | Pública | Audio continuo PCM16 mono 22050 Hz |
| POST /api/transport | action start/stop/skip/settings | Estado de audio |
| POST /api/transport | action settings, autodj boolean, crossfade 0.2–12, master 0–1, manual_mix 0–1 | Estado |
| POST /api/deck | deck 0/1, action load, track id | Carga manual; AutoDJ apagado |
| POST /api/deck | deck 0/1, action play/cue/gain, value 0–1.5 para gain | Estado |
| POST /api/jingle | track id | Jingle en cola, máximo 4 |
| POST /api/playlists | name, tracks array ordenado de ids | Nueva lista 201 |
| POST /api/playlist/activate | id o null (biblioteca completa) | Lista base |
| POST /api/schedules | name, playlist id, days 0–6 (lunes=0), start/end minutos 0–1440, priority 0–100 | Bloque 201 |
| POST /api/schedule/delete | id | Elimina bloque |
| POST /api/live/acquire | {} | lease_seconds 3, sample_rate 22050 |
| POST /api/live/chunk | PCM16LE mono 22050 Hz binario | Renueva concesión; máximo 1 s por petición, cola 2 s |
| POST /api/live/release | {} | Cierra solo micro propio |
| POST /api/research | track id | Investigación borrador, citas, fecha, modelo |
| POST /api/claim | track id, claim {text,kind,url,reviewer} | Revisión editorial persistente |
| POST /api/script | track id, seconds 15/30/60 | Texto, fuentes, estado editorial_draft |

Los tipos de claim son fact, artist_statement e interpretation. La API exige enlace HTTPS pero no visita ni valida el contenido; quien registra la revisión confirma que lo leyó. La sesión usa clave compartida y reviewer es texto libre.

La salida de estado incluye nombres de archivo internos, no rutas de acceso arbitrarias. No existen endpoints de ejecución, eliminación de medios, edición de listas ni importación por URL. Los controles no tienen clave de idempotencia: no reintentes automáticamente creaciones ante respuesta de red incierta.
