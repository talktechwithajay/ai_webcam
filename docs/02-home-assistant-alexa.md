# 02 – Home Assistant + Alexa announcement test (Milestone 1)

Sources: <https://www.home-assistant.io/integrations/alexa_devices/> and the automation webhook-trigger docs (checked 2026-10-11).

## 1. Add the Alexa Devices integration
1. Settings → Devices & services → **Add Integration** → **Alexa Devices**.
2. Enter the Amazon account email, password and the **one-time code from an authenticator app**.
3. MFA is mandatory and **SMS codes are not supported**. In Amazon: *Login & Security → 2-step verification → Backup methods → Add new app*, and make the authenticator your preferred method.
4. `CannotAuthenticate` usually means wrong credentials or non-app 2FA. Test by logging into your Amazon site in a private window.
5. Credentials are entered only in the HA UI. Never put them in this repo or `.env`.

## 2. Find the real notify entity (do not guess)
Each Echo exposes a **Speak** and an **Announce** notify entity (Announce plays the chime first).
Developer Tools → **States** → filter `notify.` → note the exact entity ID for your Echo Dot. Then test it manually in Developer Tools → **Actions**:
```yaml
action: notify.send_message
target:
  entity_id: notify.<your_real_entity_id>
data:
  message: "Test from Home Assistant"
```
**Milestone 1 gate:** the Echo Dot must speak this. Only then continue.

## 3. Create the webhook automation
```powershell
python tools\test_announcement.py --generate-id      # copy the printed ID
```
1. Create `.env` from `.env.example`; set `HA_BASE_URL` (`http://homeassistant.local:8123` or `http://<vm-ip>:8123`) and `HA_WEBHOOK_ID` (the generated ID).
2. HA → Automations → Create → *Edit in YAML*, paste `homeassistant/automation_visitor_announce.yaml`, and replace `<WEBHOOK_ID>` and `<ECHO_NOTIFY_ENTITY>` in the HA editor only (the repo file keeps placeholders).
3. The automation uses `local_only: true`, POST only, speaks only templates it owns (chosen by `message_key`), sanitises names, drops events older than 60 s, and suppresses non-health messages 22:00–07:00. Adjust quiet hours there for now; Milestone 5 moves them into the app settings.

## 4. Test
```powershell
python tools\test_announcement.py --dry-run          # validate the payload offline
python tools\test_announcement.py                     # real send
python tools\test_announcement.py --key welcome_home --name Aryan   # outside quiet hours
```
HTTP 200 only proves HA received the event. In HA, open the automation → Traces to see whether it ran or stopped at a condition, and confirm the Echo spoke.

## Troubleshooting
| Symptom | Likely cause |
|---|---|
| HTTP 404 from webhook | Wrong webhook ID, or automation disabled |
| Trace stops at condition | Quiet hours, event older than 60 s (clock skew between Windows and VM), or unknown `message_key` |
| `Could not reach Home Assistant` | VM not running, wrong IP, or Bridged Adapter bound to the wrong NIC |
| No speech but trace succeeded | Wrong notify entity, Echo offline, or Amazon rate limiting (the docs note rate-limit warnings in logs) |
| Alexa integration login fails | Non-app 2FA or credentials; see section 1 |
