FROM python:3.13-slim-bookworm AS radio
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY server/ server/
COPY public/ public/
COPY scripts/ scripts/
RUN useradd --uid 10001 --create-home radio && mkdir /data && chown radio:radio /data
USER radio
ENV HOST=0.0.0.0 RADIO_DATA=/data PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["python", "-m", "server.app"]

FROM python:3.13-slim-bookworm AS icecast
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends icecast2 && rm -rf /var/lib/apt/lists/*
COPY scripts/icecast_entry.py /app/icecast_entry.py
USER icecast2
EXPOSE 8000
CMD ["python", "/app/icecast_entry.py"]
