# Validación de entrega · 13 noviembre 2026

Entorno: macOS, Python 3.14.1, Node 24.14.1. Python 3.13 es el objetivo de Docker y CI. Sin paquetes Python externos.

- Suite local: 15 pruebas, 14 aprobadas y una omitida porque FFmpeg no está instalado.
- Comprobación de sintaxis JavaScript para consola y AudioWorklet: aprobada.
- Compilación sintáctica Python: aprobada.
- Navegador integrado: login correcto, biblioteca demo, inicio de transporte, pista en A, siguiente preparada en B, medidor real, monitor de aire con reproductor en estado de reproducción, transición A→B, historial de pista terminada y generación de guion neutro con título/artista de demo.
- Revisión visual de consola a ancho reducido: sin desbordamiento del layout principal; las tablas tienen scroll horizontal.

No validados en este entorno: Docker, Compose, FFmpeg/MP3, Icecast real, consulta de pago OpenAI, captura de micrófono físico, separación de dispositivos de audio, compatibilidad Safari/Firefox, carga prolongada ni emisión pública. La prueba de OpenAI usa un proveedor simulado para verificar extracción de citas y que el resultado conserva estado borrador.

El monitor se observó reproduciendo en el navegador; no se mide aquí la calidad acústica en altavoces físicos. La salida PCM y el avance independiente del navegador sí se comprobaron en pruebas de integración.

CI está configurado para instalar FFmpeg y construir contenedores; revisar su ejecución en GitHub Actions antes del despliegue de una emisora real. La publicación del código no implica haber desplegado la estación ni activado Pages.
