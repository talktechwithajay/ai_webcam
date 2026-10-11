# Milestone 1 report – Environment and Alexa

**Status: NOT complete.** Scaffolding and tooling are done; the acceptance gate (Echo Dot speaks a test message) has not been met and cannot be met until the manual steps below are done.

## Environment findings (inspected 2026-10-11)
| Item | Result |
|---|---|
| OS | Windows 11 Home 10.0.26200 |
| CPU / RAM | Core Ultra 9 185H, 16C/22T, 31.5 GB |
| Python | 3.13.1 present; **3.12 not installed** (available via winget, 3.12.10) |
| Git / Node | 2.49.0 / v24.15.0 present |
| VS Code | present (`E:\Microsoft VS Code`) |
| VirtualBox | **not installed** |
| Hypervisor | Hyper-V/VBS running → HAOS in VirtualBox may be slow (see docs/01) |
| Cameras | Only the built-in **Intel AVStream Camera** detected. **No USB webcams are visible.** |
| Sleep | AC: never; battery: 30 min |

## Implemented
- Repo scaffold, `.gitignore` blocking secrets/biometrics, `.env.example`.
- `scripts/check-environment.ps1`, `install-prerequisites.ps1`, `prevent-sleep.ps1`.
- `tools/list_cameras.py` (probe, snapshot, preview).
- `tools/test_announcement.py` (stdlib; strict closed-vocabulary event validation; secret never printed).
- `homeassistant/automation_visitor_announce.yaml` (template selection by `message_key`, name sanitising, stale-event drop, quiet hours).
- Guides: `docs/01-windows-setup.md`, `docs/02-home-assistant-alexa.md`. HAOS and Alexa steps were taken from the official HA pages, fetched today.

## Tests actually run
- `check-environment.ps1`: ran, output above is real.
- `test_announcement.py`: ID generation OK; valid payload OK; injection-style name rejected; arbitrary message key rejected; missing config gives a clean error. No network send was attempted.
- Automation YAML: parses as valid YAML. **Not tested inside Home Assistant** (no HA instance exists yet), so the Jinja templates are unverified.
- `list_cameras.py`: **not run** (OpenCV not installed yet, no venv).

## Manual actions for you
1. Install Python 3.12 and VirtualBox (`docs/01` §1; VirtualBox needs an admin shell).
2. Build the HAOS VM (`docs/01` §3) and finish onboarding.
3. Add Alexa Devices (authenticator-app MFA), find the Echo Dot notify entity, and make it speak from Developer Tools.
4. Create the webhook automation and run `python tools\test_announcement.py`.
5. Plug in both USB webcams, then `python tools\list_cameras.py --snapshots`.
6. Tell me the results (or any errors) and I'll fix the templates/guides.

## Acceptance criteria for Milestone 2
- Both webcams are discovered and identified as front-door/indoor via the diagnostic.
- Echo Dot test announcement confirmed to speak (M1 gate).
- Python 3.12 venv works; FastAPI backend serves camera status/MJPEG preview with auto-reconnect; test-video mode works without hardware; Vue dashboard shows both cameras' status. No face recognition yet.
