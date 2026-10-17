# 03 – Connecting the CP Plus DVR/NVR cameras

The system reads each camera as an RTSP video stream from your recorder. Nothing is recorded or changed on the recorder.

> **Honesty note.** CP Plus recorders are generally rebranded Dahua devices, so the default URL below is the Dahua format. This was written from public Dahua/CP Plus guidance and **has not been tested against your recorder** (none was available when this was built). `check-cameras` tells you exactly what works.

## 1. On the recorder (once)
1. Find the recorder's LAN IP (recorder menu → Network, or your router's device list). Give it a fixed IP / DHCP reservation so it does not change.
2. Create a **view-only user** (recorder menu → Account/User). Give it live-view permission for the front-door and indoor channels only. Do not use the admin account.
3. Make sure RTSP is on (default port **554**; menu → Network → Port).
4. If you can choose the video codec per channel, use **H.264** (not H.265): OpenCV decodes it everywhere.
5. Note which **channel number** is the front door and which is indoor (the number shown in the recorder's live view, starting at 1).

Quick test before touching this project: open VLC → Media → Open Network Stream →
`rtsp://USER:PASSWORD@RECORDER_IP:554/cam/realmonitor?channel=1&subtype=0`
If VLC shows video, this project will too.

## 2. In `config/settings.local.yaml`
```yaml
recorder:
  host: 192.168.1.108      # your recorder
  rtsp_port: 554
  username: viewer
  password: "the-password" # special characters are fine
cameras:
  front_door:
    role: front
    source: recorder
    channel: 1             # front-door channel on the recorder
    detect_subtype: 1      # light stream, watched continuously
    snapshot_subtype: 0    # full-resolution, fetched only when someone is confirmed
  indoor:
    role: indoor
    source: recorder
    channel: 2
```
Why two streams: the sub stream keeps CPU use low while watching; when a face is confirmed the system grabs one sharp full-resolution frame, which gives clearer pictures and noticeably better recognition.

## 3. Check it
```powershell
scripts\run.ps1 check-config      # shows what was understood (passwords hidden)
scripts\run.ps1 check-cameras     # connects, decodes, runs face detection, saves test snapshots to data\camera_check\
```
Delete `data\camera_check\` afterwards (personal data).

### If `check-cameras` fails
| Message | What to try |
|---|---|
| `cannot open ...` | Wrong IP/port/user/password, RTSP disabled, or the URL path differs for your model. Test in VLC. |
| Works in VLC but not here | Set `recorder.rtsp_url_template` (see below) to the exact URL pattern that works in VLC. |
| `connected but no frame decoded` | Stream is H.265 → switch the channel to H.264 on the recorder. |
| Wrong picture on a channel | Channel numbering differs; try neighbouring numbers. |
| Another recorder brand/path | Use `source: rtsp` and paste the full URL into `rtsp_url`. |

Template placeholders: `{username} {password} {host} {port} {channel} {subtype}`. The default is the Dahua pattern `rtsp://{username}:{password}@{host}:{port}/cam/realmonitor?channel={channel}&subtype={subtype}`. If your recorder uses a different path, copy the exact URL that works in VLC into the template (or use `source: rtsp` with the full URL).

## 4. Picture quality tips
- Recognition needs a face at least ~70 px wide (setting `min_face_px`). Mount the front-door camera at face height facing the approach; a camera looking down from a high corner gives poor results.
- Good light on the face (avoid strong backlight from the doorway).
- Analog (DVR) cameras can be low resolution; if faces are tiny, expect more "unknown" results.
- Use `zone: [x1, y1, x2, y2]` (fractions of the frame) to ignore the street.

## 5. USB webcam or test video instead
```yaml
cameras:
  front_door: {role: front, source: usb, usb_index: 0}
  indoor:     {role: indoor, source: file, path: tests/sample.mp4}   # video or image file
```
