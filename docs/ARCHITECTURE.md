# Arquitectura

```text
Navegador operador ── HTTP autenticado ── Python ThreadingHTTPServer
  decks/cue local      JSON / PCM16           │
  AudioWorklet ──────────────────────── concesión de micrófono (3 s)
                                              │
SQLite + WAV ── preparación fuera del reloj ──┤
                                              ▼
                    Deck A + Deck B → crossfade → ducking + voz + jingles
                                              │
                                      master / clamp PCM16
                                              │
                     /stream.wav público ─────┼── navegador / VLC
                                              └── FFmpeg → Icecast /radio.mp3
OpenAI Responses + web_search → borrador con citas → revisión → guion local
```

## Audio

Reloj monotónico en un hilo dedicado: bloques de 1024 muestras a 22050 Hz, mono PCM16. La preparación carga las dos pistas completas fuera del reloj; máximo 30 minutos por archivo. Los decodificadores no dependen de procesos de navegador. WAV nativo no necesita FFmpeg; al importar otros formatos se normaliza formato, no sonoridad.

La transición usa coseno/seno de potencia constante. Master y un clamp numérico evitan desbordamiento; no son un limitador de sonoridad profesional. Se evita escribir bloques en el disco. SQLite registra fin de pistas dentro del render; un disco bloqueado puede causar discontinuidades. Para despliegues exigentes hace falta una cola de persistencia desacoplada.

Cada monitor tiene una cola limitada (~1 segundo). Si es lento, pierde bloques antiguos. Máximo 20 monitores directos. La emisión WAV usa tamaños RIFF de streaming; la compatibilidad depende del cliente. Icecast MP3 es la ruta recomendada para oyentes públicos. No hay WebSocket/WebRTC ni retorno de baja latencia.

El preparador rota secuencialmente según la lista activa o bloque semanal. Se decide cada carga, no cada muestra. Un cambio horario puede encontrar una pista ya precargada. El estado de transporte y la posición son efímeros; el servidor reinicia detenido. No hay reloj de emisión exacta ni reglas antirrepetición.

## Vivo y takeover

AudioWorklet captura micrófono mono, remuestrea por selección de muestras a 22050 Hz y envía paquetes PCM de 4096 muestras. El remuestreo es básico, sin filtro antialias profesional. Cola del servidor limitada a dos segundos. Se cierra el micro si el navegador detecta envíos más lentos que el ritmo de captura.

La sesión reclama una concesión exclusiva de tres segundos. Cada paquete renueva la concesión. Al expirar se descarta la cola y vuelve AutoDJ a su nivel previo. Música al 18% durante la concesión; salida de voz con master aunque transporte musical esté detenido. El takeover externo futuro debe conservar esta regla de caducidad en el servidor, añadir identidad por usuario y puente WebRTC → PCM antes de la mezcla.

Dos pestañas que comparten cookie también comparten identidad; solo se garantiza exclusividad entre sesiones distintas. El estado de micrófono del navegador no sustituye al indicador del servidor.

## Datos y seguridad

SQLite WAL guarda un documento JSON con biblioteca, listas, parrilla, historial, investigación y guiones. Bloqueo reentrante para modificaciones compuestas y snapshots. Medios con UUID generado por servidor; no se aceptan rutas arbitrarias ni URLs de audio. No hay migraciones versionadas todavía.

Clave de estudio comparada con tiempo constante, sesiones aleatorias en memoria de 12 horas, cookies HttpOnly/SameSite=Strict y cabecera en mutaciones. Sin CORS, rutas estáticas permitidas explícitamente y CSP. No hay cuentas ni RBAC. La identidad del revisor es una anotación editorial, no una firma criptográfica.

## Copiloto

Solo título/artista se envían a OpenAI. No se envían audios ni letras. `research` conserva texto, anotaciones de citas, fecha y modelo. No transforma un resultado en hecho verificado. Una afirmación revisada registra tipo, enlace HTTPS, editor y fecha. El guion es determinista, sin llamada de IA, y usa solamente esas afirmaciones junto a metadatos del operador.

## Extensiones prioritarias

1. Cola de persistencia e importación desacoplada con límites de CPU/memoria.
2. WebRTC/Opus, estéreo y remuestreo de calidad.
3. Identidad por locutor, permisos y auditoría inmutable.
4. Programación de reloj exacto y anti repetición.
5. Normalización R128, limitador y alertas de silencio.
6. Tests de navegador, carga prolongada y matriz de dispositivos reales.
