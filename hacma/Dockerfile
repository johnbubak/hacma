# Nutzen Sie ein schlankes Linux-Image mit Python 3.11 - natürlich
FROM python:3.11-slim

# Das Build-Argument für die Zielarchitektur
ARG TARGETARCH 

# Alle Installationsschritte in einem einzigen RUN-Befehl
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        git \
        ca-certificates \
        libyaml-dev \
        python3-dev && \
		
    pip install PyYAML && \
    
    # 1. Bestimme die Architektur für Docker Compose basierend auf TARGETARCH
    if [ "$TARGETARCH" = "amd64" ]; then \
        COMPOSE_ARCH="x86_64"; \
    elif [ "$TARGETARCH" = "arm64" ]; then \
        COMPOSE_ARCH="aarch64"; \
    else \
        # Standardmäßig x86_64, falls Architektur unbekannt
        COMPOSE_ARCH="x86_64"; \
    fi; \
    
    # 2. Installiere docker-compose-cli (V2.24.5)
    curl -SL "https://github.com/docker/compose/releases/download/v2.24.5/docker-compose-linux-$COMPOSE_ARCH" -o /usr/local/bin/docker-compose && \
    chmod +x /usr/local/bin/docker-compose && \
    
    # 3. Aufräumen
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Kopiere das Kern-Skript
COPY run.py /

# Setze den Startbefehl
CMD [ "python3", "/run.py" ]
