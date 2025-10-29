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
TARGET_ADDON_DIR_IN_REPO = "local"                         # Der Zielordner im Repository (z.B. Ihr 'local'-Repo-Ordner)

# --- HILFSFUNKTIONEN (unverändert) --- 
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
        
    # Kopiere config.yaml und run.sh in das Zielverzeichnis (der Compose-Ordner wird NICHT benötigt)
    os.makedirs(target_dir, exist_ok=True)
    shutil.copy(os.path.join(addon_dir, 'config.yaml'), target_dir)
    shutil.copy(os.path.join(addon_dir, 'run.sh'), target_dir)
    print(f"[GitHub] Neue Add-on-Dateien kopiert nach: {target_dir}")
    
    commit_message = f"feat(addon): Neuer Add-on '{addon_name}' generiert via HACMA"
    
    if not run_command(f"git add .", cwd=GITHUB_REPO_DIR):
        return False
        
    if not run_command(f"git commit -m \"{commit_message}\" --allow-empty", cwd=GITHUB_REPO_DIR):
        pass # Kann fehlschlagen, wenn keine Änderung, ist OK
        
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
    
    # --- 2. Overrides injizieren ---
    
    service = first_service
    
    # --- 2.1 Top-Level Definitionen (volumes, networks) ---
    def parse_and_inject_top_level(key, options, target_data):
        # 'top_level_volumes' -> 'volumes'
        yaml_string = options.get(f"top_level_{key}")
        if yaml_string:
            try:
                parsed_val = yaml.safe_load(yaml_string)
                if isinstance(parsed_val, dict):
                    target_data[key] = parsed_val
                    print(f"[Override] Top-Level '{key}' injiziert.")
            except yaml.YAMLError as e:
                print(f"[FEHLER] Ungültige YAML-Syntax in Top-Level '{key}': {e}")
    
    parse_and_inject_top_level('volumes', options, compose_data)
    parse_and_inject_top_level('networks', options, compose_data)


    # --- 2.2 Service Overrides injizieren ---
    
    # Einfache Strings
    for key in ['image', 'container_name', 'restart']:
        if options.get(key): 
            service[key] = options[key]
            print(f"[Override] {key} injiziert: {service[key]}")
        
    # Komplexe YAML-Block Overrides
    def parse_and_inject_yaml(key, options, target_service):
        yaml_string = options.get(key)
        if yaml_string:
            try:
                parsed_val = yaml.safe_load(yaml_string)
                if parsed_val is not None:
                    target_service[key] = parsed_val
                    print(f"[Override] {key} injiziert.")
                    return True
            except yaml.YAMLError as e:
                print(f"[FEHLER] Ungültige YAML-Syntax in {key}: {e}")
        return False

    parse_and_inject_yaml('ports', options, service)
    parse_and_inject_yaml('volumes', options, service)
    parse_and_inject_yaml('devices', options, service)
    parse_and_inject_yaml('command', options, service)
    parse_and_inject_yaml('networks', options, service)
    
    # environment (Spezialfall: Update/Merge)
    env_vars_yaml_string = options.get('environment')
    if env_vars_yaml_string:
        try:
            env_vars_parsed = yaml.safe_load(env_vars_yaml_string)
            if env_vars_parsed:
                current_env_dict = {}
                existing_env = service.get('environment', {}) 
                
                if isinstance(existing_env, list):
                    for item in existing_env:
                        if isinstance(item, str) and '=' in item:
                            k, v = item.split('=', 1)
                            current_env_dict[k] = v
                elif isinstance(existing_env, dict):
                    current_env_dict.update(existing_env)
                
                if isinstance(env_vars_parsed, dict):
                     current_env_dict.update(env_vars_parsed)
                elif isinstance(env_vars_parsed, list):
                     for item in env_vars_parsed:
                        if isinstance(item, str) and '=' in item:
                            k, v = item.split('=', 1)
                            current_env_dict[k] = v
                
                service['environment'] = current_env_dict
                print(f"[Override] environment injiziert/aktualisiert.")
                
        except yaml.YAMLError as e:
            print(f"[FEHLER] Ungültige YAML-Syntax in environment: {e}")


    # --- 3. Lokale Dateistruktur vorbereiten & Schreiben ---
    
    # Altes Add-on herunterfahren und löschen (Lokales Deployment)
    if os.path.exists(addon_dir):
        compose_config_dir_tmp = os.path.join(HACMA_CONFIG_PATH, addon_name)
        compose_path_in_config_tmp = os.path.join(compose_config_dir_tmp, 'docker-compose.yaml')
        if os.path.exists(compose_path_in_config_tmp):
             run_command(f"/usr/local/bin/docker-compose -f {compose_path_in_config_tmp} -p {addon_name} down", cwd=compose_config_dir_tmp)
             
        shutil.rmtree(addon_dir)
        
    os.makedirs(addon_dir, exist_ok=True)
    os.makedirs(os.path.join(addon_dir, 'compose'), exist_ok=True) # compose-Ordner wird erstellt, aber nicht genutzt

    # Schreibe die ÜBERSCHRIEBENE Compose-Datei in den /config-Ordner (für Benutzer-Zugriff)
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
    
    run_sh_content = f"""#!/