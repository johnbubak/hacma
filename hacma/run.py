import json
import os
import shutil
import sys
import subprocess
import yaml

# --- KONSTANTEN ---
OPTIONS_FILE = "/data/options.json"
# Das lokale Add-on Repo auf dem HAOS Host.
ADDONS_BASE_PATH = "/usr/share/hassio/addons/local"

# --- HILFSFUNKTIONEN --- 

def load_options():
    """Lädt die Konfiguration des Compose Managers."""
    if not os.path.exists(OPTIONS_FILE):
        print("Fehler: Konfigurationsdatei nicht gefunden.")
        sys.exit(1)
    with open(OPTIONS_FILE, 'r') as f:
        return json.load(f)

def update_manager_options(new_options_content):
    """Schreibt die Optionen des Compose Managers zurück (für den Lade-Mechanismus)."""
    try:
        with open(OPTIONS_FILE, 'w') as f:
            json.dump(new_options_content, f, indent=2)
        print("\n[Manager-Update] Optionen erfolgreich aktualisiert. Bitte HA Frontend neu laden (F5).")
    except Exception as e:
        print(f"[Manager-Update] FEHLER beim Schreiben der Manager-Optionen: {e}")

def run_command(command, cwd=None):
    """Führt einen Shell-Befehl aus und gibt die Ausgabe zurück."""
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            check=True,
            shell=True,
            capture_output=True,
            text=True
        )
        print(f"[CMD OK] {command}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[CMD FEHLER] {command}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        return False

def get_supervisor_token():
    """Holt den Supervisor-Token für API-Aufrufe."""
    return os.environ.get('SUPERVISOR_TOKEN')

# --- 1. PROJEKTERKENNUNG ---

def get_existing_projects():
    """Sucht nach existierenden, vom Fabrikator erzeugten Projekten."""
    projects = {}
    if not os.path.exists(ADDONS_BASE_PATH):
        return projects

    for name in os.listdir(ADDONS_BASE_PATH):
        addon_dir = os.path.join(ADDONS_BASE_PATH, name)
        compose_path = os.path.join(addon_dir, 'compose', 'docker-compose.yaml')
        
        # Prüfen, ob es sich um ein Fabrikator-Projekt handelt
        if os.path.isdir(addon_dir) and os.path.exists(compose_path):
            with open(compose_path, 'r') as f:
                projects[name] = f.read()
    return projects

# --- 2. LOGIK FUNKTIONEN ---

def handle_load_config(options, projects):
    """Lädt die Compose-YAML des ausgewählten Projekts in das Editierfeld des