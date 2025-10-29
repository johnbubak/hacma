import json
import os
import shutil
import sys
import subprocess
import yaml
import re # Neu: Für das Parsen von Umgebungsvariablen

# --- KONSTANTEN ---
OPTIONS_FILE = "/data/options.json"
# Das lokale Add-on Repo auf dem HAOS Host.
ADDONS_BASE_PATH = "/usr/share/hassio/addons/local"
ADDON_CONFIG_TEMPLATE_PATH = "/config_template" # Pfad zu Ihrer Vorlagenstruktur (config.yaml, run.sh etc.)

# --- HILFSFUNKTIONEN --- 

def load_options():
    """Lädt die Konfiguration des Compose Managers (/data/options.json)."""
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
        
        # Prüfen, ob es sich um ein Fabrikator-Projekt handelt (indem nach der compose-Datei gesucht wird)
        if os.path.isfile(compose_path):
            projects[name] = compose_path
            
    return projects

def update_project_selector(current_options):
    """Aktualisiert die 'project_name_selector' Optionen und schreibt sie zurück."""
    projects = get_existing_projects()
    
    # Hier müsste eigentlich die Supervisor API verwendet werden, um das Schema zu aktualisieren.
    # Da wir keinen direkten Zugriff auf das Schema haben, dient dies nur der internen Anzeige/Logik.
    
    # In Home Assistant Add-ons wird das Schema nur beim Start gelesen.
    # Daher ist dieser Schritt primär für die Logik in run.py selbst.
    print(f"\n[Projekt-Update] Gefundene Projekte: {list(projects.keys())}")
    
    # Die tatsächliche Aktualisierung des Schemas muss manuell erfolgen. 
    # Wir protokollieren nur die Projekte und verlassen uns auf die HA-API für die Liste der Optionen, falls implementiert.

# --- 2. CONFIG LOGIK: NEU & KORRIGIERT ---

def parse_env_vars(env_vars_str):
    """Parst einen String (z.B. KEY=VALUE\nOTHER=VALUE) in eine Liste im Compose-Format."""
    if not env_vars_str:
        return []
    
    env_list = []
    # Splittet nach Zeilen und ignoriert leere Zeilen
    for line in env_vars_str.splitlines():
        line = line.strip()
        if line and '=' in line:
             env_list.append(line)
             
    return env_list

def generate_addon_config(options):
    """
    Generiert die neuen Add-on-Dateien basierend auf der Compose-YAML und den Overrides.
    """
    compose_yaml_string = options.get('compose_yaml')
    project_slug = None

    if not compose_yaml_string:
        print("[FEHLER] Compose YAML Definition fehlt.")
        return False

    try:
        compose_data = yaml.safe_load(compose_yaml_string)
    except yaml.YAMLError as e:
        print(f"[FEHLER] Ungültige Compose YAML Syntax: {e}")
        return False

    if 'services' not in compose_data or not compose_data['services']:
        print("[FEHLER] Keine 'services' in der Compose YAML gefunden.")
        return False
        
    # --- 1. Ziel-Service identifizieren (den ersten Service im Dict) ---
    service_name = list(compose_data['services'].keys())[0]
    service = compose_data['services'][service_name]
    
    # Den Compose-Projektnamen vom Service-Namen ableiten
    project_slug = re.sub(r'[^a-z0-9]+', '', service_name.lower())
    addon_name = f"compose-{project_slug}"
    addon_dir = os.path.join(ADDONS_BASE_PATH, addon_name)
    
    print(f"\n[Generierung] Starte Erstellung von Add-on '{addon_name}'")
    
    # --- 2. Overrides injizieren (Die "CasaOS"-Logik) ---
    
    # Port-Mappings
    if options.get('port_mappings'):
        service['ports'] = options['port_mappings']
        print(f"[Override] Ports injiziert: {service['ports']}")

    # Umgebungsvariablen
    env_vars_parsed = parse_env_vars(options.get('env_vars', ''))
    if env_vars_parsed:
        # Bestehende Umgebungsvariablen im Service beibehalten und neue hinzufügen/überschreiben
        existing_env = service.get('environment', [])
        
        # Konvertiere List<string> (TZ=Europa/Berlin) zu Dict
        env_dict = {}
        for item in existing_env + env_vars_parsed:
            if '=' in item:
                key, val = item.split('=', 1)
                env_dict[key] = val
            
        service['environment'] = env_dict
        print(f"[Override] Umgebungsvariablen injiziert/aktualisiert: {service['environment']}")

    # Command Override
    if options.get('command_override'):
        service['command'] = options['command_override']
        print(f"[Override] Command injiziert: {service['command']}")

    # Geräte-Mappings
    if options.get('device_mappings'):
        service['devices'] = options['device_mappings']
        print(f"[Override] Devices injiziert: {service['devices']}")

    # --- 3. Dateistruktur vorbereiten ---
    
    # Vorhandene Add-on-Struktur löschen, falls sie existiert
    if os.path.exists(addon_dir):
        shutil.rmtree(addon_dir)
        print(f"[Clean] Vorheriges Add-on Verzeichnis gelöscht: {addon_dir}")
        
    os.makedirs(addon_dir, exist_ok=True)
    os.makedirs(os.path.join(addon_dir, 'compose'), exist_ok=True)
    
    # --- 4. Compose-Datei schreiben (mit Overrides) ---
    
    compose_path = os.path.join(addon_dir, 'compose', 'docker-compose.yaml')
    with open(compose_path, 'w') as f:
        # Setzt den Namen des Compose-Projekts
        compose_data['name'] = addon_name
        yaml.dump(compose_data, f, default_flow_style=False)
    print(f"[Datei] Compose-Datei mit Overrides gespeichert: {compose_path}")

    # --- 5. config.yaml und run.sh generieren ---
    
    # (Dieser Teil setzt voraus, dass Sie eine 'config_template' Struktur mit config.yaml und run.sh haben)
    
    # Platzhalter für die config.yaml des NEUEN Add-ons
    addon_config_yaml = os.path.join(addon_dir, 'config.yaml')
    
    # Minimales config.yaml für das generierte Add-on (WICHTIG!)
    # Hinweis: Dies ist die Minimalversion. Sie müssen dies noch um Ihr tatsächliches Template ergänzen!
    config_content = {
        'name': f"Compose - {service_name}",
        'version': '1.0.0',
        'slug': addon_name,
        'description': f"Containerized service '{service_name}' via HACMA.",
        'startup': 'before', # Startet vor Home Assistant
        'boot': 'auto',
        'arch': ['amd64', 'aarch64'],
        'host_network': True,
        'map': ['homeassistant_config:rw'],
        'options': {},
        'schema': {}
    }
    with open(addon_config_yaml, 'w') as f:
        yaml.dump(config_content, f, default_flow_style=False)
    print(f"[Datei] config.yaml für Add-on '{addon_name}' generiert.")

    # run.sh für das generierte Add-on
    # (Die run.sh muss 'docker-compose up -d' im compose-Ordner ausführen)
    run_sh_content = f"""#!/bin/bash
set -e

# Wichtig: Wechseln in das Compose-Verzeichnis
cd /usr/share/hassio/addons/local/{addon_name}/compose

echo "Starting Docker Compose service..."
# Führt docker-compose up mit dem Projektnamen aus
/usr/local/bin/docker-compose -p {addon_name} up -d

# Hier könnte noch die Log-Anzeige des Dienstes folgen
echo "Service started. Check Supervisor Logs for output."

# Der run.sh-Prozess muss im Hintergrund weiterlaufen,
# damit das Add-on als 'running' gilt. Ein einfacher sleep-Loop.
while true; do
  sleep 60
done
"""
    run_sh_path = os.path.join(addon_dir, 'run.sh')
    with open(run_sh_path, 'w') as f:
        f.write(run_sh_content)
    # run.sh ausführbar machen
    os.chmod(run_sh_path, 0o755)
    print(f"[Datei] run.sh für Add-on '{addon_name}' generiert.")

    # --- 6. Supervisor API Call (Optional, um Store neu zu laden) ---
    # Idealerweise müsste hier ein API-Call an den Supervisor gesendet werden, 
    # um das neue Add-on sichtbar zu machen. Da dies kompliziert ist,
    # setzen wir auf den manuellen Store-Update durch den Nutzer.
    
    print(f"\n[ERFOLG] Add-on '{addon_name}' wurde erstellt!")
    print("Bitte den Home Assistant Add-on Store manuell aktualisieren, um das neue Add-on zu sehen.")
    return True

# --- 3. HAUPT-PROGRAMMLOGIK ---

def main():
    """Hauptfunktion des Fabrikators."""
    options = load_options()
    action = options.get('action')

    # Update des Projekt-Selectors, um verfügbare Projekte anzuzeigen
    # (Muss idealerweise im Supervisor-Schema aktualisiert werden, hier nur Log)
    update_project_selector(options)

    if action == 'none':
        print("[Aktion] Keine Aktion gewählt. Beende.")
        sys.exit(0)
    
    elif action == 'load_config':
        project_slug = options.get('project_name_selector')
        if project_slug == 'none':
            print("[Ladefehler] Bitte ein Projekt auswählen.")
            sys.exit(1)
        
        # Hier müsste die Compose-YAML des gewählten Projekts geladen und
        # in das Feld 'compose_yaml' des Managers zurückgeschrieben werden (mit update_manager_options).
        print(f"[Lade-Aktion] Logik zum Laden der Konfiguration für '{project_slug}' fehlt.")
        
        # Wichtig: Nach dem Laden muss 'action' auf 'none' zurückgesetzt werden
        # options['action'] = 'none'
        # update_manager_options(options)

    elif action == 'generate_and_up':
        if generate_addon_config(options):
            print("[Aktion] Add-on generiert und gestartet.")
        else:
            print("[Aktion] Generierung fehlgeschlagen.")
            sys.exit(1)
        
        # Wichtig: Nach der Aktion muss 'action' auf 'none' zurückgesetzt werden
        # options['action'] = 'none'
        # update_manager_options(options)
        
    elif action == 'down_and_remove':
        # Hier müsste die Logik zum Stoppen und Löschen des Add-ons implementiert werden.
        # run_command(f"/usr/local/bin/docker-compose -p {project_slug} down", cwd=ADDONS_BASE_PATH)
        # shutil.rmtree(os.path.join(ADDONS_BASE_PATH, project_slug))
        print("[Aktion] Logik zum Stoppen und Entfernen fehlt.")
        
        # Wichtig: Nach der Aktion muss 'action' auf 'none' zurückgesetzt werden
        # options['action'] = 'none'
        # update_manager_options(options)
        
    else:
        print(f"[FEHLER] Unbekannte Aktion: {action}")
        sys.exit(1)

# Startpunkt
if __name__ == "__main__":
    main()