# AI Home Visitor Recognition & Welcome-Home System

Privacy-first, locally processed visitor announcements: two USB webcams → Python/OpenCV on Windows → Home Assistant webhook → Echo Dot. Face recognition covers only voluntarily enrolled people; everyone else is "unknown". Home Assistant never does recognition and never receives images.

**Status: Milestone 1 (environment + Alexa) – scaffolding delivered, hardware steps pending. See [docs/milestone-1-report.md](docs/milestone-1-report.md).**

## Layout
```
scripts/      PowerShell: check-environment, install-prerequisites, prevent-sleep
tools/        list_cameras.py (camera discovery), test_announcement.py (HA webhook test)
homeassistant/ automation YAML (placeholders only; real IDs live in HA / .env)
docs/         setup guides and milestone reports
backend/ frontend/   (created in Milestone 2)
```

## Plan
1. **M1** env + Alexa test ← current
2. M2 camera capture + dashboard skeleton (FastAPI, Vue 3)
3. M3 person detection, zones, cooldown, dry-run mode
4. M4 enrollment, encrypted templates, matching, measured evaluation
5. M5 front-door announcements via HA (quiet hours, stale expiry)
6. M6 indoor entry state machine + welcome
7. M7 reliability, security, retention, startup automation
8. M8 final docs and release checklist

Technology choices (models, licences) are decided at M3/M4 after verifying licences and Windows install procedures; nothing is assumed now.
