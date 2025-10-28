# Nutzen Sie ein schlankes Linux-Image mit Python
FROM python:3.11-slim

# Das Build-Argument für die Zielarchitektur
ARG TARGETARCH 

# Installiere notwendige Pakete (curl für API-Aufrufe, PyYAML für das Parsing)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        git \
        ca-certificates \
        libyaml-dev \
        python3-dev && \
    pip install PyYAML && \
    # Installiere docker-compose-cli
    curl -SL https://github.com/docker/compose/releases/download/v2.24.5/docker-compose-linux-x86_64 -o /usr/local/bin/docker-compose && \
    chmod +x /usr/local/bin/docker-compose && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Installiere Docker Compose V2 für die korrekte Architektur
RUN if [ "$TARGETARCH" = "amd64" ]; then \
        COMPOSE_ARCH="x86_64"; \
    elif [ "$TARGETARCH" = "arm64" ]; then \
        COMPOSE_ARCH="aarch64"; \
    else \
        # Standardmäßig x86_64, falls Architektur unbekannt
        COMPOSE_ARCH="x86_64"; \
    fi; \
    
    # Lade die korrekte Docker Compose Binary
    curl -SL "https://github.com/docker/compose/releases/download/v2.24.5/docker-compose-linux-$COMPOSE_ARCH" -o /usr/local/bin/docker-compose && \
    chmod +x /usr/local/bin/docker-compose && \

# Kopiere das Kern-Skript
COPY run.py /

# Setze den Startbefehl
CMD [ "python3", "/run.py" ]