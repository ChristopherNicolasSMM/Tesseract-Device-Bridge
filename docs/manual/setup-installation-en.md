# Device Bridge 2.0.0 — Setup and migration

Working branch: feature/sqlite-full-migration. Installer build: 2.0.0-setup.10.
Implemented for acceptance testing; physical Raspberry/systemd qualification is
not yet certified. See [acceptance matrix](../homologacao/setup-2.0.0.md).

## Install from a clean clone

```bash
git clone --branch feature/sqlite-full-migration --single-branch https://github.com/ChristopherNicolasSMM/Tesseract-Device-Bridge.git Tesseract-Device-Bridge-SQLite
cd Tesseract-Device-Bridge-SQLite
python -m venv venv
```

Activate venv: Windows .\venv\Scripts\Activate.ps1;
Linux source venv/bin/activate. Then:

```bash
python -m pip install -r requirements.txt
python -m setup
```

Open http://127.0.0.1:8090. Do not create .env or SQLite first.
Setup supports language/theme, an empty database, YAML/JSON folders, uploads and
consistent SQLite snapshots. Previous installations are read-only sources.
Never run setup as root. Raspberry physical GPIO retains its Python 3.9 requirement.

For a remote Raspberry, use ssh -N -L 8090:127.0.0.1:8090 user@raspberry,
then open the same local address. Keep the same host/port during the session.

## Review and complete

Import writes only to private staging. Select inventory entries, inspect formatted
redacted previews and review events. Unknown files are ignored. JSON catalogs may
be imported partially only with explicit consent; critical invalid device data
never creates an operational candidate.

SQLite WAL/SHM/journal sidecars are rejected: stop the old runtime and provide a
consistent backup; never delete sidecars to force acceptance.
Limits: 8 MiB per YAML/JSON, 32 MiB total, 256 MiB SQLite.

Configure infrastructure, then choose generated token, custom token or local-only
administration without a token. Short custom values are allowed with a warning.
Generated tokens are shown once and are never stored in browser cookies.
Base64 credential storage is serialization, not encryption.

Without a token, the panel binds to 127.0.0.1. Administrative writes require
loopback, exact local Host, same origin and session CSRF. Remote/proxy requests
are rejected. Legacy deployments without explicit local policy remain disabled.

Publication requires a nonexistent final DB and explicit .env replacement consent
when applicable. A publishing receipt blocks runtime until both files are ready.
Successful setup completion replaces the temporary ORM-only-simulation barrier;
it never starts physical outputs. Existing thermal, gas and emergency interlocks remain.

Empty installs open configuration-only administration without DeviceRuntime/GPIO/MQTT.
Review-blocked installations remain simulated. Revalidation requires correction,
review and explicit configured-mode authorization.

## Recovery, services and acceptance

Restart setup after interruption and use Resume or rollback of that incomplete attempt.
A completed installation cannot be deleted by Cancel.
Use local NTFS/ext4 with hard-link support.

Systemd generation, installation, enabling and starting are separate actions.
Windows uses manual execution. The managed scripts do not overwrite old units.
Stop processes before backing up .env and all data/private, including receipt/setup state.

```bash
python -m setup.doctor
python -m pytest -q
python run_bridge.py
```

The doctor is read-only and does not validate wiring or expose credentials.
Code updates use git pull --ff-only; do not repeat legacy import over a published DB.
See the [full Portuguese manual](20-instalacao-migracao-2.0.0.md) and
[backup/recovery guide](21-manutencao-recuperacao.md).
