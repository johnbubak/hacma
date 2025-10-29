# Nutzen Sie ein schlankes Linux-Image mit Python 3.11
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
    
    # NEU: Installiere requests für den URL-Download
    pip install PyYAML requests && \
    
    # 1. Bestimme die Architektur für Docker Compose basierend auf TARGETARCH
    if [ "$TARGETARCH" = "amd64" ]; then \
        COMPOSE_ARCH="x86_64"; \
    elif [ "$TARGETARCH" = "arm64" ]; then \
        COMPOSE_ARCH="aarch64"; \
    else \
        COMPOSE_ARCH="x86_64"; \
    fi; \
    
    # 2. Installiere docker-compose-cli (V2.24.5)
    # Verwenden Sie das -L Flag, um Redirects zu folgen (was GitHub oft tut)
    curl -SL "https://github.com/docker/compose/releases/download/v2.24.5/docker-compose-linux-$COMPOSE_ARCH" -o /usr/local/bin/docker-compose && \
    chmod +x /usr/local/bin/docker-compose && \
    
    # 3. Aufräumen
    apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Kopieren Sie die Python-Logik
COPY run.py /
# Fügen Sie den run.sh Starter hinzu
COPY run.sh /
# Fügen Sie die Add-on-Konfiguration hinzu
COPY config.yaml /
# Fügen Sie die Add-on-Dokumentation hinzu (falls vorhanden)
# COPY README.md /

CMD [ "/run.sh" ]