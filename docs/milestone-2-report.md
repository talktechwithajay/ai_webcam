# Milestone 2 report – full software implementation

**Status: software complete and tested in isolation. NOT verified against your real CP Plus recorder, Home Assistant VM or Echo Dot** (none exist in this environment). Read "What was NOT verified" before relying on it.

## Built
- **Cameras:** CP Plus recorder over RTSP/TCP (URL template in config, credentials URL-encoded and masked), generic RTSP, USB webcam, or image/video file for testing. Latest-frame reader thread, reconnect with backoff, stale detection. Sub-stream for continuous watching, full-resolution grab only when a face is confirmed.
- **Recognition:** YuNet face detection + SFace embeddings via OpenCV (CPU). Tracker requires N frames, picks the best frame, applies zones, per-person cooldown, one visit per face (several people = several visits).
- **Storage:** SQLite; pictures, thumbnails and embeddings encrypted (Fernet); unknown people saved as `UNKNOWN #n`; naming a person renames all their visits; merge, split ("Not them"), delete; retention purge (default 90 days, or never).
- **Announcements:** front door (named / unknown), indoor (custom message per person with date/weekday rules, else "Welcome home"), per-person and global mute, quiet hours, dry-run (default on), cooldowns, async delivery to the HA webhook, camera-offline alert.
- **Dashboard (Vue 3):** Visits with date filter and pictures, Visitors list + per-visitor table, Unknown people, Indoor messages, Announcements (mutes), Cameras (status + live view), Settings (retention, dry-run, quiet hours). Login with rate limiting.
- **Operations:** `scripts\setup.ps1`, `run.ps1` (`check-config`, `check-cameras`, `seed-demo`), `install-startup.ps1`, `tools\download_models.py` (checksum-verified).

## Verified (what I actually ran)
| Check | Result |
|---|---|
| `pytest` | 53 tests pass: config/URL building, DB rules (rename-all, retention, merge, messages), announcement decisions, webhook delivery against a local fake HA server, pipeline with a fake face engine (multi-person, cooldown, mutes, indoor rules), API incl. login lockout |
| Real face models | Downloaded with checksums. On sample images: Lena image → new `UNKNOWN #1`; second camera showing an unrelated photo was ignored indoors; after naming "Lena", a flipped/darker copy was matched to Lena |
| Dashboard in a browser | Login, Visits list with pictures and date presets, naming an unknown person from the Visits page (all visits renamed), Visitors grid, Settings (90 → Never delete persisted across reload), mobile width without horizontal scroll |
| `check-cameras` failure path | Unreachable recorder gives a readable error with credentials masked |
| `setup.ps1` | Ran end to end (venv, deps, models, frontend build, config copy, tests) |

## What was NOT verified
- **A real CP Plus recorder.** The RTSP URL is the Dahua pattern from public guides; your model may differ. `check-cameras` is how you find out. H.265 streams may need switching to H.264.
- **Home Assistant / Alexa.** The updated automation YAML parses, but the Jinja templates have never run in HA. Test with `python tools\test_announcement.py --key custom_message --name Naresh --text "Hello"` after pasting it.
- **Recognition accuracy.** Defaults (`match_threshold: 0.40`, min face 70 px) are not measured on your cameras. Expect more "unknown" at night or with small/angled faces; measure before trusting names. A printed photo can fool any face recogniser (no liveness check).
- **Scheduled startup** (`install-startup.ps1`) was syntax-checked only.
- **Long-running stability** (days of RTSP, memory use) was not tested.

## Known limitations
- Amazon credentials cannot be read from the config file: Home Assistant's Alexa integration must be linked in HA's own UI (needs authenticator-app 2FA). The config file holds only the HA webhook ID.
- Dashboard is plain HTTP on your LAN. Do not expose it to the internet.
- `data/secret.key` encrypts everything; losing it makes stored pictures unreadable, leaking it with the data folder exposes them.

## Next steps for you
See handbook §19 "Your manual steps".
