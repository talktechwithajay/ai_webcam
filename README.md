# AI Home Visitor Recognition & Welcome-Home System

Privacy-first, locally processed visitor log and announcements. CP Plus CCTV (DVR/NVR, via RTSP) or USB webcams → Python/OpenCV on Windows → browser dashboard + Home Assistant webhook → Echo Dot.

- Recognises only people you have named; everyone else is **UNKNOWN #n** until you name them (all their past visits are renamed at once).
- Home Assistant only speaks messages; it never does recognition and never receives pictures.
- Pictures and face data stay on this laptop, encrypted, with a retention period you choose (default 90 days, or never delete).

**Status: implemented end to end; automated tests pass; real-model test done on sample images. NOT yet tested against your CP Plus recorder, Home Assistant VM or Echo Dot** – see [docs/milestone-2-report.md](docs/milestone-2-report.md) for exactly what was and was not verified.

## Quick start
```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1       # venv, models, dashboard build, creates config\settings.local.yaml
notepad config\settings.local.yaml                                # recorder IP/login, dashboard password, Home Assistant webhook
scripts\run.ps1 check-config
scripts\run.ps1 check-cameras                                     # proves each camera connects and sees faces
scripts\run.ps1                                                   # dashboard at http://localhost:8080
powershell -ExecutionPolicy Bypass -File scripts\install-startup.ps1   # optional: auto-start at sign-in
```
No cameras yet? `scripts\run.ps1 seed-demo` fills the dashboard with demo visitors.

## Documentation
| Doc | Content |
|---|---|
| [00_ai_webcam_project_handbook.md](00_ai_webcam_project_handbook.md) | Requirements, architecture, decisions, risks, to-do list |
| [docs/01-windows-setup.md](docs/01-windows-setup.md) | Python, VirtualBox, Home Assistant OS VM, keep-awake |
| [docs/02-home-assistant-alexa.md](docs/02-home-assistant-alexa.md) | Alexa Devices integration, webhook automation, test |
| [docs/03-cp-plus-cameras.md](docs/03-cp-plus-cameras.md) | Connecting the CP Plus recorder, troubleshooting |
| [docs/04-using-the-dashboard.md](docs/04-using-the-dashboard.md) | Every page and how recognition behaves |
| [docs/milestone-2-report.md](docs/milestone-2-report.md) | What was built, tested, and what you still must do |

## Layout
```
backend/ahv/     Python: config, camera sources, face engine, pipeline, announcer, API, CLI
backend/tests/   pytest suite (53 tests)
frontend/        Vue 3 dashboard (npm run build -> frontend/dist, served by the backend)
config/          settings.example.yaml (copy to settings.local.yaml, git-ignored)
homeassistant/   automation YAML (placeholders only)
tools/           download_models.py, test_announcement.py, list_cameras.py
scripts/         setup, run, install-startup, prevent-sleep, check-environment
models/ data/    (git-ignored) face models; database, encrypted pictures, encryption key
```

## Security & privacy summary
- Dashboard is password-protected (rate-limited login, signed cookie) and should only be reachable on your home network; do not port-forward it.
- Pictures, embeddings are encrypted with `data/secret.key`. **Back that key up and enable BitLocker**; whoever has the key and the data folder can read the pictures.
- `config/settings.local.yaml`, `.env`, `data/` and `models/` are git-ignored. Never commit them.
- Face recognition is not a security control. Do not use it to unlock anything.
