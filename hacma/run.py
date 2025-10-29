import json
import os
import shutil
import sys
import subprocess
import yaml
import re
import requests
from urllib.parse import urlparse

# --- KONSTANTEN ---
OPTIONS_FILE = "/data/options.json"
ADDONS_BASE_PATH = "/usr/share/hassio/addons/local"
HACMA_CONFIG_PATH = "/config/hacma/projects" 
# GITHUB KONSTANTEN
GITHUB_REPO_URL = "https://github.com/johnbubak/hacma.git" 
GITHUB_REPO_DIR = "/tmp/hacma_git_repo"                    
GITHUB_BRANCH = "main"
TARGET_ADDON_DIR_IN_REPO = "local"                         

# --- HILFSFUNKTIONEN --- 

def load_options():
    if not os.path.exists(OPTIONS_FILE):
        print("Fehler: Konfigurationsdatei nicht gefunden.")
        sys.exit(1)
    with open(OPTIONS_FILE, 'r') as f:
        return json.load(f)

def update_manager_options(new_options_content):
    try:
        with open(OPTIONS_FILE, 'w') as f:
            json.dump(new_options_content, f, indent=2)
        print("\n[Manager-Update] Optionen erfolgreich aktualisiert. Bitte HA Frontend neu laden (F5).")
    except Exception as e:
        print(f"[Manager-Update] FEHLER beim Schreiben der Manager-Optionen: {e}")

def run_command(command, cwd=None):
    try:
        # GitHub-Token im Log unterdrücken
        clean_command = re.sub(r'https://.*@', 'https://[TOKEN_REMOVED]@', command)
        
        result = subprocess.run(
            command,
            cwd=cwd,
            check=True,
            shell=True,
            capture_output=True,
            text=True
        )
        print(f"[CMD OK] {clean_command}")
        return True
    except subprocess.CalledProcessError as e:
        clean_command = re.sub(r'https://.*@', 'https://[TOKEN_REMOVED]@', command)
        print(f"[CMD FEHLER] {clean_command}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        return False

def get_existing_projects():
    projects = {}
    if not os.path.exists(ADDONS_BASE_PATH):
        return projects

    for name in os.listdir(ADDONS_BASE_PATH):
        if name.startswith('compose-'):
            addon_dir = os.path.join(ADDONS_BASE_PATH, name)
            config_path = os.path.join(addon_dir, 'config.yaml')
            if os.path.isfile(config_path):
                projects[name] = config_path
                
    return projects

def update_project_selector(current_options):
    projects = get_existing_projects()
    print(f"\n[Projekt-Update] Gefundene Projekte: {list(projects.keys())}")
    return projects

def download_compose_file(url):
    print(f"\n[Download] Starte Download von: {url}")
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()

        compose_data = yaml.safe_load(response.text)

        if not isinstance(compose_data, dict) or 'services' not in compose_data:
            print("[FEHLER] Heruntergeladener Inhalt ist keine gültige Compose-Datei.")
            return None
            
        print("[Download] Compose-Datei erfolgreich heruntergeladen und validiert.")
        return compose_data
        
    except requests.exceptions.RequestException as e:
        print(f"[FEHLER] Fehler beim Herunterladen der URL: {e}")
        return None
    except yaml.YAMLError as e:
        print(f"[FEHLER] Ungültige YAML-Syntax in der heruntergeladenen Datei: {e}")
        return None

def publish_addon_to_github(addon_name, addon_dir, pat):
    if os.path.exists(GITHUB_REPO_DIR):
        shutil.rmtree(GITHUB_REPO_DIR)
        
    os.makedirs(GITHUB_REPO_DIR, exist_ok=True)
    
    parsed_url = urlparse(GITHUB_REPO_URL)
    auth_url = f"{parsed_url.scheme}://{pat}@{parsed_url.netloc}{parsed_url.path}"
    
    print(f"\n[GitHub] Klone Repository {GITHUB_REPO_URL}...")
    if not run_command(f"git clone {auth_url} {GITHUB_REPO_DIR}", cwd="/tmp"):
        print("[FEHLER] Klonen des Repositories fehlgeschlagen. PAT prüfen.")
        return False
        
    run_command("git config user.email 'hacma@addon.local'", cwd=GITHUB_REPO_DIR)
    run_command("git config user.name 'HACMA Add-on Fabrikator'", cwd=GITHUB_REPO_DIR)
    
    target_dir = os.path.join(GITHUB_REPO_DIR, TARGET_ADDON_DIR_IN_REPO, addon_name)
    
    if os.path.exists(target_dir):
        shutil.rmtree(target_dir)
        print(f"[GitHub] Vorherige Add-on-Dateien im Repo gelöscht: {target_dir}")
        
    # Kopiere config.yaml und run.sh in das Zielverzeichnis
    os.makedirs(target_dir, exist_ok=True)
    shutil.copy(os.path.join(addon_dir, 'config.yaml'), target_dir)
    shutil.copy(os.path.join(addon_dir, 'run.sh'), target_dir)
    print(f"[GitHub] Neue Add-on-Dateien kopiert nach: {target_dir}")
    
    commit_message = f"feat(addon): Neuer Add-on '{addon_name}' generiert via HACMA"
    
    if not run_command(f"git add .", cwd=GITHUB_REPO_DIR):
        return False
        
    if not run_command(f"git commit -m \"{commit_message}\" --allow-empty", cwd=GITHUB_REPO_DIR):
        pass 
        
    print("[GitHub] Pushe Änderungen...")
    if not run_command(f"git push origin {GITHUB_BRANCH}", cwd=GITHUB_REPO_DIR):
        return False
        
    print(f"\n[VERÖFFENTLICHUNG ERFOLG] Add-on '{addon_name}' wurde erfolgreich in GitHub veröffentlicht.")
    return True


# --- 2. HAUPT-LOGIK: GENERIERUNG ---

def generate_addon_config(options):
    
    compose_url = options.get('compose_url')
    if not compose_url:
        print("[FEHLER] Compose URL fehlt.")
        return False

    compose_data = download_compose_file(compose_url)
    if not compose_data:
        return False

    if 'services' not in compose_data or not compose_data['services']:
        print("[FEHLER] Keine 'services' in der Compose YAML gefunden.")
        return False
        
    # Projekt-Namen ableiten
    service_name = list(compose_data['services'].keys())[0]
    first_service = compose_data['services'][service_name]
    base_name = first_service.get('image', service_name)
    project_slug = re.sub(r'[^a-z0-9]+', '', base_name.lower())
    addon_name = f"compose-{project_slug}"
    addon_dir = os.path.join(ADDONS_BASE_PATH, addon_name)
    
    print(f"\n[Generierung] Starte Erstellung von Add-on '{addon_name}'")
    
    # Den ersten Service zum Überschreiben auswählen
    service = first_service
    
    # --- 2.1 Top-Level Definitionen (volumes, networks) ---
    def parse_and_inject_top_level_list(key, options, target_data):
        """Konvertiert eine Liste von Strings (z.B. 'db_data', 'db_data: { driver: local }') 
           in das notwendige Top-Level-Dictionary."""
        override_list = options.get(f"top_level_{key}")
        if override_list and isinstance(override_list, list) and override_list:
            
            parsed_dict = {}
            for item in override_list:
                item = item.strip()
                if not item:
                    continue
                
                try:
                    # Versuche, den String als YAML zu parsen (für komplexe Definitionen)
                    item_yaml = yaml.safe_load(item)
                    if isinstance(item_yaml, dict):
                         parsed_dict.update(item_yaml)
                    elif isinstance(item_yaml, str):
                         # Wenn es nur ein Name ist, setze leeres Dict (Standard-Treiber)
                         parsed_dict[item_yaml] = {} 
                    
                except Exception:
                    # Fallback auf einfachen Namen
                    parsed_dict[item] = {}
                    
            if parsed_dict:
                target_data[key] = parsed_dict
                print(f"[Override] Top-Level '{key}' injiziert.")

    parse_and_inject_top_level_list('volumes', options, compose_data)
    parse_and_inject_top_level_list('networks', options, compose_data)
    
    # --- 2.2 Service Overrides injizieren ---
    
    # Einfache Strings
    for key in ['image', 'container_name', 'restart']:
        if options.get(key): 
            service[key] = options[key]
            print(f"[Override] {key} injiziert: {service[key]}")
        
    # --- Injection for simple Lists (ports, volumes, devices, command, networks) ---
    def inject_list_override(key, options, target_service):
        """Injiziert einfache Listen-Overrides (ports, volumes, devices, command, networks)."""
        override_list = options.get(key)
        # Prüfen, ob es eine nicht leere Liste von Strings ist
        if override_list and isinstance(override_list, list) and all(isinstance(item, str) for item in override_list) and override_list:
            target_service[key] = override_list
            print(f"[Override] {key} injiziert.")
            return True
        return False

    inject_list_override('ports', options, service)
    inject_list_override('volumes', options, service)
    inject_list_override('devices', options, service)
    inject_list_override('command', options, service)
    inject_list_override('networks', options, service)
    
    # environment (Spezialfall: Update/Merge, list(str) im Format KEY=VALUE)
    env_vars_list = options.get('environment')
    if env_vars_list and isinstance(env_vars_list, list) and env_vars_list:
        try:
            current_env_dict = {}
            existing_env = service.get('environment', {}) 
            
            # 1. Existierendes Environment in Dict konvertieren
            if isinstance(existing_env, list):
                for item in existing_env:
                    if isinstance(item, str) and '=' in item:
                        k, v = item.split('=', 1)
                        current_env_dict[k] = v
            elif isinstance(existing_env, dict):
                current_env_dict.update(existing_env)
            
            # 2. Neue Liste mergen (Überschreiben)
            for item in env_vars_list:
                item = item.strip()
                if isinstance(item, str) and '=' in item:
                    k, v = item.split('=', 1)
                    current_env_dict[k] = v
            
            service['environment'] = current_env_dict
            print(f"[Override] environment injiziert/aktualisiert.")
                
        except Exception as e:
            print(f"[FEHLER] Fehler beim Parsen von environment (Liste): {e}")


    # --- 3. Lokale Dateistruktur vorbereiten & Schreiben ---
    
    if os.path.exists(addon_dir):
        compose_config_dir_tmp = os.path.join(HACMA_CONFIG_PATH, addon_name)
        compose_path_in_config_tmp = os.path.join(compose_config_dir_tmp, 'docker-compose.yaml')
        if os.path.exists(compose_path_in_config_tmp):
             run_command(f"/usr/local/bin/docker-compose -f {compose_path_in_config_tmp} -p {addon_name} down", cwd=compose_config_dir_tmp)
             
        shutil.rmtree(addon_dir)
        
    os.makedirs(addon_dir, exist_ok=True)
    os.makedirs(os.path.join(addon_dir, 'compose'), exist_ok=True) 

    # Speichere die ÜBERSCHRIEBENE Compose-Datei in den /config-Ordner 
    compose_config_dir = os.path.join(HACMA_CONFIG_PATH, addon_name)
    os.makedirs(compose_config_dir, exist_ok=True)
    compose_path_in_config = os.path.join(compose_config_dir, 'docker-compose.yaml')
    
    with open(compose_path_in_config, 'w') as f:
        compose_data['name'] = addon_name 
        yaml.dump(compose_data, f, default_flow_style=False, sort_keys=False)
    print(f"[Datei] Überschriebene Compose-Datei gespeichert in: {compose_path_in_config}")

    # --- 4. config.yaml und run.sh für das NEUE Add-on generieren ---
    
    addon_config_yaml = os.path.join(addon_dir, 'config.yaml')
    config_content = {
        'name': f"Compose - {service_name}", 
        'version': '1.0.0',
        'slug': addon_name,
        'description': f"Containerized service '{service_name}' via HACMA. Config: {compose_path_in_config}",
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
    
    run_sh_content = f"""#!/bin/bash
set -e

COMPOSE_FILE_PATH="{compose_path_in_config}"
COMPOSE_DIR=$(dirname $COMPOSE_FILE_PATH)
PROJECT_NAME="{addon_name}"
SERVICE_NAME="{service_name}"

echo "Using Compose file from: $COMPOSE_FILE_PATH"

cd $COMPOSE_DIR

echo "Starting Docker Compose service..."
/usr/local/bin/docker-compose -f $COMPOSE_FILE_PATH -p $PROJECT_NAME up -d

echo "Service started in detached mode. Checking logs..."

CONTAINER_NAME=$(/usr/local/bin/docker-compose -f $COMPOSE_FILE_PATH -p $PROJECT_NAME ps -q $SERVICE_NAME)

if [ -z "$CONTAINER_NAME" ]; then
    echo "Logs können nicht getailt werden: Container für Service '$SERVICE_NAME' nicht gefunden. Bitte Supervisor Terminal für Logs überprüfen."
else
    echo "Container Name: $CONTAINER_NAME"
    echo "Tailing logs. Press Ctrl+C in Supervisor Terminal to detach..."
    /usr/bin/docker logs -f $CONTAINER_NAME
fi
"""
    run_sh_path = os.path.join(addon_dir, 'run.sh')
    with open(run_sh_path, 'w') as f:
        f.write(run_sh_content)
    os.chmod(run_sh_path, 0o755)

    print(f"\n[ERFOLG] Add-on '{addon_name}' wurde lokal erstellt und installiert.")
    
    # --- 5. GITHUB VERÖFFENTLICHUNG ---
    if options.get('publish_addon') is True:
        pat = options.get('github_pat')
        if pat:
            publish_addon_to_github(addon_name, addon_dir, pat)
        else:
            print("[FEHLER] 'publish_addon' ist aktiv, aber 'github_pat' fehlt. Veröffentlichung abgebrochen.")

    return True

# --- 3. HAUPT-PROGRAMMLOGIK (unverändert) ---

def main():
    options = load_options()
    action = options.get('action')
    update_project_selector(options)

    if action == 'none':
        sys.exit(0)
    
    elif action == 'generate_and_up':
        if generate_addon_config(options):
            print("[Aktion] Add-on generiert und gestartet.")
        else:
            sys.exit(1)
        
        options['action'] = 'none'
        options['publish_addon'] = False 
        update_manager_options(options)
        
    elif action == 'down_and_remove':
        project_slug = options.get('project_name_selector')
        if project_slug == 'none':
            sys.exit(1)
            
        addon_dir = os.path.join(ADDONS_BASE_PATH, project_slug)
        compose_config_dir = os.path.join(HACMA_CONFIG_PATH, project_slug) 

        if os.path.exists(addon_dir):
            compose_path_in_config = os.path.join(compose_config_dir, 'docker-compose.yaml')
            if os.path.exists(compose_path_in_config):
                 run_command(f"/usr/local/bin/docker-compose -f {compose_path_in_config} -p {project_slug} down", cwd=compose_config_dir)
            
            shutil.rmtree(addon_dir)
            if os.path.exists(compose_config_dir):
                shutil.rmtree(compose_config_dir)
        
        options['project_name_selector'] = 'none'
        options['action'] = 'none'
        options['publish_addon'] = False 
        update_manager_options(options)
        
    elif action == 'load_config':
        project_slug = options.get('project_name_selector')
        compose_path_in_config = os.path.join(HACMA_CONFIG_PATH, project_slug, 'docker-compose.yaml')
        
        if project_slug != 'none' and os.path.exists(compose_path_in_config):
            try:
                with open(compose_path_in_config, 'r') as f:
                    loaded_yaml_data = yaml.safe_load(f)
                    loaded_yaml_data.pop('name', None) 
                    loaded_yaml_string = yaml.dump(loaded_yaml_data, default_flow_style=False, sort_keys=False)
                    
                    print("\n--- GELADENE COMPOSE-YAML ---")
                    print(loaded_yaml_string)
                    print("-----------------------------")

            except Exception as e:
                print(f"[Ladefehler] Fehler beim Lesen der Compose-Datei: {e}")
        else:
            print("[Ladefehler] Projekt oder Compose-Datei nicht gefunden.")

        options['action'] = 'none'
        options['publish_addon'] = False 
        update_manager_options(options)
        
    else:
        print(f"[FEHLER] Unbekannte Aktion: {action}")
        sys.exit(1)

if __name__ == "__main__":
    main()