# 04 – Using the dashboard

Open `http://localhost:8080` (or `http://<laptop-ip>:8080` from another device on your Wi-Fi if `dashboard.host` is `0.0.0.0`). Sign in with the username/password from `config/settings.local.yaml`.

| Page | What it does |
|---|---|
| **Visits** | Every person the cameras noticed: picture, who, when, camera, what was announced. Quick date buttons (Today, Yesterday, Last 7/30 days, All time) plus From/To dates; filter by camera or known/unknown. Two people arriving together = two rows. "Name this person" on any unknown row. |
| **Visitors** | One card per unique person (named and unknown) with visit count, first/last seen. Click one for a clean table of all their visits (date filter, sort by time, pictures, match %, announcement). On that page you can name/rename, mute, merge duplicates, mark a visit "Not them", delete. **Add a person from photos** enrols someone directly (consent tick-box required). |
| **Unknown people** | Everyone not yet named, grouped by face. Name them (all past visits rename instantly), merge with someone else, or delete. |
| **Indoor messages** | Per-person text Alexa says when the indoor camera recognises them, e.g. Naresh → "Welcome Naresh, today please make Aloo Paratha!". Optional date range and weekdays; newest matching message wins; no message → "Welcome home, Naresh." |
| **Announcements** | **Mute everything** switch, a mute switch per person, front-door "unknown visitor" on/off, indoor greetings on/off, test button. Muted people are still logged. |
| **Cameras** | Online/offline status, resolution, fps, errors, live preview. |
| **Settings** | Keep pictures of unknown people for N days (default **90**) or **Never delete**; real-vs-dry-run announcements; quiet hours; log unknown people seen indoors. |

## How recognition works day to day
1. A face must be seen in several frames (default 3) before it counts, so passers-by and glitches are ignored.
2. The best frame is saved as a cropped, encrypted picture; the face is compared with everyone stored.
3. Known person → announced by name. No match → a new **UNKNOWN #n** person is created (or the existing UNKNOWN #n they match is reused).
4. Name an unknown person → they become known and **all** their past visits show the new name.
5. Indoor camera: only named people are greeted; unrecognised faces are ignored unless you enable logging them in Settings.
6. Repeat sightings of the same person within the cooldown (front door 60 s, indoor 30 min for announcements) do not repeat the announcement.

## Good habits
- Start in **dry-run** (the default). Watch the Visits page for a few days: messages appear there but Alexa stays quiet. Then tick "Send real announcements" in Settings.
- Fix mistakes right away: **Not them** splits a wrong match out; **Merge** joins two entries for one person. Both improve future matching.
- Only enrol or name people who know the cameras recognise them. Pictures of unknown visitors are stored (deleted after your retention period); camera notices may be legally required in your area.
