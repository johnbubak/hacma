# HA-Addon-Fabricator

## HACMA - Home Assistant Compose Manager Add-on

[![GitHub Release][releases-shield]][releases]
[![License][license-shield]][license]

Home Assistant Add-on Repository für den **HACMA - Compose Manager the HomeAssistant Addon Fabrikator**.

## 🚀 Was ist HACMA?

HACMA (Home Assistant Compose Manager Add-on) ist ein leistungsstarkes Werkzeug, das es ermöglicht, **jedes Docker Compose Projekt in ein eigenständiges, lokales Home Assistant Add-on zu verwandeln und zu verwalten.**

Anstatt manuell Add-ons zu erstellen, nutzt der Fabrikator die von Ihnen bereitgestellte Compose-Definition, generiert die notwendigen Konfigurationsdateien (`config.json`, `run.sh`) und verwendet `docker-compose` für den Betrieb der Dienste im Home Assistant Supervisor-Ökosystem.

## 🛠️ Installation

Um dieses Add-on nutzen zu können, müssen Sie dieses Repository als Add-on-Quelle in Home Assistant hinzufügen.

1.  Gehen Sie in Home Assistant zu **Einstellungen** > **Add-ons**.
2.  Klicken Sie unten rechts auf die **drei Punkte (⋮)**.
3.  Wählen Sie **"Repositories"**.
4.  Fügen Sie die folgende URL hinzu:
    `https://github.com/johnbubak/hacma`
5.  Installieren Sie das Add-on **"HA-Addon-Fabricator"**.

## ⚙️ Verwendung

Nach der Installation des HACMA-Managers:

1.  Gehen Sie zum **Konfiguration**-Tab des HACMA Add-ons.
2.  Fügen Sie Ihre Docker Compose YAML-Definition in das Feld **"2. Compose YAML Definition"** ein.
3.  Wählen Sie unter **"3. Aktion"** die Option **`generate_and_up`**.
4.  Klicken Sie auf **Speichern**.

Der Manager generiert nun ein neues Add-on basierend auf Ihrem Compose-Dienst. Sie müssen dann das **neu generierte Add-on** (z.B. `compose-meindienst`) separat starten.

***

[releases-shield]: https://img.shields.io/github/release/johnbubak/HA-Addon-Fabricator.svg?style=for-the-badge
[releases]: https://github.com/johnbubak/HA-Addon-Fabricator/releases
[license-shield]: https://img.shields.io/github/license/johnbubak/HA-Addon-Fabricator.svg?style=for-the-badge
[license]: https://github.com/johnbubak/HA-Addon-Fabricator/blob/main/LICENSE
