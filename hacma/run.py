import json
import os
import shutil
import sys
import subprocess
import yaml
import re

# --- KONSTANTEN ---
OPTIONS_FILE = "/data/options.json"
# Das lokale Add-on Repo auf dem HAOS Host.
ADDONS_BASE_PATH = "/usr/share/hassio/addons/local"

# --- HILFSFUNKTIONEN --- 

def load_options():
    """Lädt die Konfiguration des Compose Managers (/data/options.json)."""
    if not os.path.exists(OPTIONS_FILE):
        print("Fehler: Konfigurationsdatei nicht gefunden.")
        sys.exit(1)
    with open(OPTIONS_FILE, 'r') as f:
        return json.load(f)

def update_manager_options(new_options_content):
    """Schreibt die Optionen des Compose Managers zurück (für das Zurücksetzen der Aktion)."""
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
        # Wir geben True zurück, wenn der Befehl fehlschlägt, um den Fabrikator nicht abstürzen zu lassen,
        # wenn ein Add-on nicht gestoppt werden kann (z.B. down_and_remove)
        return False

def get_existing_projects():
    """Sucht nach existierenden, vom Fabrikator erzeugten Projekten."""
    projects = {}
    if not os.path.exists(ADDONS_BASE_PATH):
        return projects

    for name in os.listdir(ADDONS_BASE_PATH):
        # Nur compose-Projekte berücksichtigen
        if name.startswith('compose-'):
            addon_dir = os.path.join(ADDONS_BASE_PATH, name)
            compose_path = os.path.join(addon_dir, 'compose', 'docker-compose.yaml')
            
            if os.path.isfile(compose_path):
                projects[name] = compose_path
                
    return projects

def update_project_selector(current_options):
    """Prüft existierende Projekte und loggt sie (da Schema-Update per API komplex ist)."""
    projects = get_existing_projects()
    print(f"\n[Projekt-Update] Gefundene Projekte: {list(projects.keys())}")
    # Hier müsste die API verwendet werden, um project_name_selector zu aktualisieren.
    # Da dies im Add-on nur schwer möglich ist, wird dieser Teil nur geloggt.
    return projects

# --- 2. CONFIG LOGIK: FINAL ---

def generate_addon_config(options):
    """
    Generiert die neuen Add-on-Dateien basierend auf der Compose-YAML und den Overrides.
    Beachtet die List-Eingabetypen aus der config.yaml.
    """
    
    # --- 1. Compose YAML laden (als Liste der Zeilen) ---
    # compose_yaml ist jetzt eine Liste von Strings (eine Zeile pro Element)
    compose_yaml_list = options.get('compose_yaml', [])
    if not compose_yaml_list:
        print("[FEHLER] Compose YAML Definition fehlt.")
        return False

    # Liste der Zeilen zu einem einzigen String zusammenfügen
    compose_yaml_string = '\n'.join(compose_yaml_list) 

    try:
        compose_data = yaml.safe_load(compose_yaml_string)
    except yaml.YAMLError as e:
        print(f"[FEHLER] Ungültige Compose YAML Syntax: {e}")
        return False

    if 'services' not in compose_data or not compose_data['services']:
        print("[FEHLER] Keine 'services' in der Compose YAML gefunden.")
        return False
        
    # --- 2. Ziel-Service identifizieren (den ersten Service im Dict) ---
    service_name = list(compose_data['services'].keys())[0]
    service = compose_data['services'][service_name]
    
    # Den Compose-Projektnamen vom Service-Namen ableiten
    project_slug = re.sub(r'[^a-z0-9]+', '', service_name.lower())
    addon_name = f"compose-{project_slug}"
    addon_dir = os.path.join(ADDONS_BASE_PATH, addon_name)
    
    print(f"\n[Generierung] Starte Erstellung von Add-on '{addon_name}'")
    
    # --- 3. Overrides injizieren ---
    
    # Ports (ist bereits eine Liste von Strings durch list(str) im Schema)
    port_mappings = options.get('port_mappings')
    if port_mappings:
        # Fügt die neuen Ports hinzu, überschreibt aber die alten, falls vorhanden
        service['ports'] = port_mappings
        print(f"[Override] Ports injiziert/überschrieben: {service['ports']}")

    # Umgebungsvariablen (ist jetzt auch eine Liste von Strings durch list(str)?)
    env_vars_list = options.get('env_vars')
    if env_vars_list:
        # Bestehende Umgebungsvariablen im Service beibehalten und neue hinzufügen/überschreiben
        existing_env = service.get('environment', {}) # Kann Dict oder Liste sein
        
        # Konvertiere alle zu einem Dictionary für einfaches Überschreiben
        env_dict = {}
        
        # Bestehende Umgebungsvariablen in Dict konvertieren
        if isinstance(existing_env, list):
             for item in existing_env:
                if '=' in item:
                    key, val = item.split('=', 1)
                    env_dict[key] = val
        elif isinstance(existing_env, dict):
            env_dict.update(existing_env)

        # Neue Umgebungsvariablen aus der Liste hinzufügen/überschreiben
        for item in env_vars_list:
            item = item.strip()
            if item and '=' in item:
                key, val = item.split('=', 1)
                env_dict[key] = val
            
        # Compose V3 bevorzugt das Dictionary-Format
        service['environment'] = env_dict
        print(f"[Override] Umgebungsvariablen injiziert/aktualisiert: {service['environment']}")

    # Command Override (ist ein einfacher String)
    command_override = options.get('command_override')
    if command_override:
        service['command'] = command_override
        print(f"[Override] Command injiziert: {service['command']}")

    # Geräte-Mappings (ist bereits eine Liste von Strings)
    device_mappings = options.get('device_mappings')
    if device_mappings:
        service['devices'] = device_mappings
        print(f"[Override] Devices injiziert/überschrieben: {service['devices']}")

    # --- 4. Dateistruktur vorbereiten & Schreiben ---
    
    # Vorhandene Add-on-Struktur löschen, falls sie existiert
    if os.path.exists(addon_dir):
        # Stoppen des Compose-Dienstes vor dem Löschen versuchen
        run_command(f"/usr/local/bin/docker-compose -p {addon_name} down", cwd=os.path.join(addon_dir, 'compose'))
        shutil.rmtree(addon_dir)
        print(f"[Clean] Vorheriges Add-on Verzeichnis gelöscht: {addon_dir}")
        
    os.makedirs(addon_dir, exist_ok=True)
    os.makedirs(os.path.join(addon_dir, 'compose'), exist_ok=True)
    
    # Compose-Datei schreiben (mit Overrides)
    compose_path = os.path.join(addon_dir, 'compose', 'docker-compose.yaml')
    with open(compose_path, 'w') as f:
        compose_data['name'] = addon_name
        yaml.dump(compose_data, f, default_flow_style=False, sort_keys=False) # sort_keys=False für bessere Lesbarkeit
    print(f"[Datei] Compose-Datei mit Overrides gespeichert: {compose_path}")

    # --- 5. config.yaml und run.sh für das NEUE Add-on generieren ---
    
    addon_config_yaml = os.path.join(addon_dir, 'config.yaml')
    
    # Minimales config.yaml (kann später erweitert werden)
    config_content = {
        'name': f"Compose - {service_name}",
        'version': '1.0.0',
        'slug': addon_name,
        'description': f"Containerized service '{service_name}' via HACMA. Base Image: {service.get('image', 'n/a')}",
        'startup': 'before',
        'boot': 'auto',
        'arch': ['amd64', 'aarch64'],
        'host_network': True,
        'map': ['homeassistant_config:rw'],
        'options': {},
        'schema': {}
    }
    with open(addon_config_yaml, 'w') as f:
        yaml.dump(config_content, f, default_flow_style=False, sort_keys=False)
    print(f"[Datei] config.yaml für Add-on '{addon_name}' generiert.")

    # run.sh für das generierte Add-on (startet den Dienst)
    run_sh_content = f"""#!/bin/bash
set -e

# Wichtig: Wechseln in das Compose-Verzeichnis
cd {addon_dir}/compose

echo "Starting Docker Compose service..."
# Führt docker-compose up mit dem Projektnamen aus
/usr/local/bin/docker-compose -p {addon_name} up -d

echo "Service started in detached mode. Checking logs..."

# Hier muss das Skript aktiv bleiben, damit der Supervisor den Add-on-Status als 'running' sieht.
# Ansonsten würde das Add-on sofort wieder stoppen.
# Wir verwenden Tail auf dem Log des ersten Containers (angenommen, er existiert und schreibt Logs).

CONTAINER_NAME=$(/usr/local/bin/docker-compose -p {addon_name} ps -q {service_name})

if [ -z "$CONTAINER_NAME" ]; then
    echo "ERROR: Container for service '{service_name}' not found after startup."
else
    echo "Container Name: $CONTAINER_NAME"
    echo "Tailing logs. Press Ctrl+C in Supervisor Terminal to detach..."
    # Folgt den Logs des Hauptcontainers
    /usr/bin/docker logs -f $CONTAINER_NAME
fi

# Wenn der Log-Tail beendet wird, hält auch das Add-on an.

"""
    run_sh_path = os.path.join(addon_dir, 'run.sh')
    with open(run_sh_path, 'w') as f:
        f.write(run_sh_content)
    os.chmod(run_sh_path, 0o755)
    print(f"[Datei] run.sh für Add-on '{addon_name}' generiert.")

    print(f"\n[ERFOLG] Add-on '{addon_name}' wurde erstellt!")
    print("Bitte den Home Assistant Add-on Store manuell aktualisieren, um das neue Add-on zu sehen.")
    return True

# --- 3. HAUPT-PROGRAMMLOGIK ---

def main():
    """Hauptfunktion des Fabrikators."""
    options = load_options()
    action = options.get('action')

    # Update des Projekt-Selectors (für Logging)
    update_project_selector(options)

    if action == 'none':
        print("[Aktion] Keine Aktion gewählt. Beende.")
        sys.exit(0)
    
    elif action == 'generate_and_up':
        if generate_addon_config(options):
            print("[Aktion] Add-on generiert und gestartet.")
        else:
            print("[Aktion] Generierung fehlgeschlagen.")
            sys.exit(1)
        
        # Wichtig: Nach der Aktion muss 'action' auf 'none' zurückgesetzt werden
        options['action'] = 'none'
        update_manager_options(options)
        
    elif action == 'down_and_remove':
        project_slug = options.get('project_name_selector')
        if project_slug == 'none':
            print("[Löschfehler] Bitte ein Projekt auswählen.")
            sys.exit(1)
            
        addon_dir = os.path.join(ADDONS_BASE_PATH, project_slug)
        if os.path.exists(addon_dir):
            print(f"[Aktion] Lösche Projekt '{project_slug}'...")
            
            # 1. Compose Dienst stoppen und entfernen
            run_command(f"/usr/local/bin/docker-compose -p {project_slug} down", cwd=os.path.join(addon_dir, 'compose'))
            
            # 2. Add-on-Verzeichnis löschen
            shutil.rmtree(addon_dir)
            print(f"[Aktion] Verzeichnis gelöscht: {addon_dir}")
        else:
            print(f"[Löschfehler] Projektverzeichnis '{project_slug}' nicht gefunden.")
        
        # Zurücksetzen und Update
        options['project_name_selector'] = 'none'
        options['action'] = 'none'
        update_manager_options(options)
        
    # Die Aktionen 'load_config' und 'down_and_remove' benötigen noch Logik
    elif action == 'load_config':
        # Da load_config komplex ist und die Supervisor-API erfordert, hier nur ein Platzhalter:
        print("[Lade-Aktion] Die Logik zum Laden der Konfiguration ist komplex und erfordert die Supervisor-API. Funktion übersprungen.")
        options['action'] = 'none'
        update_manager_options(options)
        
    else:
        print(f"[FEHLER] Unbekannte Aktion: {action}")
        sys.exit(1)

# Startpunkt
if __name__ == "__main__":
    main()