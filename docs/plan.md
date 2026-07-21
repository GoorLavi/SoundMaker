# SoundMaker — Implementation Plan

Tracks what's done, what's in progress, and what's next. Each phase builds on the previous one. Frontend work is embedded in each phase alongside its backend.

---

## Phase 0: Project Scaffolding
> **Status: DONE**

- [x] Create `master/backend/` directory structure
- [x] Create `requirements.txt` (fastapi, uvicorn, httpx)
- [x] Create `state_manager.py` — JSON state persistence with atomic writes
- [x] Create `main.py` — FastAPI entry point with `/api/health` and `/api/config`
- [x] Create `.gitignore` (node_modules, pycache, .venv, state/*.json, .env, .DS_Store)
- [x] Verify backend runs locally on macOS

---

## Phase 1: Pi-hole
> **Status: DONE**

- [x] Research Pi-hole v6 API (session-based auth, new REST endpoints)
- [x] Create `master/pihole.toml` — config template (Cloudflare + Google DNS, port 8080)
- [x] Create `pihole_api.py` — async Pi-hole v6 client with session auth and auto-renewal
- [x] Add Pi-hole endpoints to `main.py` (`/api/pihole/status`, `enable`, `disable`)
- [x] Graceful degradation when Pi-hole is unreachable
- [x] Create `master/install_master.sh` — unattended Pi-hole install, venv setup, systemd service
- [x] Fix port 80 permission issue (`AmbientCapabilities=CAP_NET_BIND_SERVICE`)
- [x] Deploy and verify on Raspberry Pi 5
- [x] Update `architecture.md` with actual v6 implementation details
- [x] Create `README.md`

---

## Phase 2: Web UI Scaffolding + Pi-hole UI
> **Status: DONE**

### Frontend setup
- [x] Create React app in `master/frontend/` (Vite + React, minimal dependencies)
- [x] Mobile-first responsive layout with a clean dashboard shell
- [x] Build to `dist/`, commit to repo (no Node.js needed on Pi)
- [x] FastAPI serves `dist/` as static files (already wired in `main.py`)

### Pi-hole section (first UI feature)
- [x] Blocking toggle (on/off)
- [x] Stats: queries today, blocked today, percentage
- [x] Link to Pi-hole admin UI (`http://<master>:8080/admin`)

### Bug fix
- [x] Pi-hole v6 returns `"enabled"`/`"disabled"` strings, not booleans — normalize to `true`/`false` in `pihole_api.py`

### Deploy & verify
- [x] Build on macOS, push, pull on Pi
- [x] Verify Web UI loads at `http://master.local/`
- [x] Verify Pi-hole toggle works (enable/disable blocking)
- [x] Verify Pi-hole stats display correctly

---

## Phase 2.5: Remote Access & Security
> **Status: DONE**

### Backend authentication
- [x] Create `auth.py` — bcrypt password hashing, persistent session store (`state/sessions.json`), `require_auth` FastAPI dependency
- [x] Long-lived sessions (10-year TTL) and cookie — "remember me forever" after first login; sessions survive backend restarts
- [x] Add login rate limiting (5 attempts/min per IP)
- [x] Add auth endpoints to `main.py` (`/api/auth/login`, `/api/auth/logout`, `/api/auth/check`)
- [x] Protect existing API routes with `Depends(require_auth)`
- [x] Add `passlib[bcrypt]` and `python-multipart` to `requirements.txt`

### Frontend authentication
- [x] Create shared `api.js` fetch wrapper with 401 handling
- [x] Create `LoginScreen` component (password form, dark theme)
- [x] Add auth state to `App.jsx` (auth check on mount, conditional render, logout button)
- [x] Update `PiholeCard.jsx` to use `apiFetch`

### Tailscale VPN
- [x] Add Tailscale install section to `install_master.sh`
- [x] Add `SOUNDMAKER_PW` password hashing to install script (bcrypt directly; passlib was incompatible with bcrypt 4.1+)
- [x] Install Tailscale on Master Pi and authenticate (`sudo tailscale up --ssh`)
- [x] Install Tailscale app on phone and verify remote Web UI access

### Documentation
- [x] Update `architecture.md` — new sections 19 (Authentication) and 20 (Remote Access), updated Security table
- [x] Update `plan.md` — add Phase 2.5
- [x] Update `README.md` — remote access instructions
- [x] Document Tailscale URL format (`http://master.<tailnet>.ts.net/`) and how to find tailnet (`tailscale dns status`)

---

## Phase 2.6: Manual Self-Update + Versioned Migrations
> **Status: DONE**

### Backend
- [x] Create `update_manager.py` — version from git, check remote (git fetch + compare), apply (lock, git pull, pip install, migrations)
- [x] State: `version.json` (current, last_updated_at), `applied_migrations.json`, `update.lock`
- [x] Migrations: `master/migrations/*.sh` run in order, recorded in `applied_migrations.json`; env `SOUNDMAKER_STATE_DIR`, `SOUNDMAKER_REPO`
- [x] Add `master/migrations/001_initial.sh` (no-op)
- [x] API: `GET /api/updates/status`, `POST /api/updates/check`, `POST /api/updates/apply`, `GET /api/updates/progress`

### Frontend
- [x] Create `UpdatesCard.jsx` — System → Updates: current version, last update, Check for updates, Apply update (when available), progress log, success/failure

### Documentation
- [x] `architecture.md` — §16 Updates and Migrations (how updates work, Web UI, API, versioning, migrations, adding migrations, Web UI vs SSH, safety)
- [x] `architecture.md` — state (version.json, applied_migrations.json, update.lock), project structure (update_manager, migrations/, UpdatesCard)
- [x] `plan.md` — Phase 2.6

---

## Phase 2.7: System tab (Master health dashboard)
> **Status: DONE**

### Backend
- [x] Create `system_info.py` — read-only gathering of CPU (model, frequency, load), memory, temperature, storage, network (interface, IP, Wi-Fi SSID/signal, internet), OS (version, uptime, hostname), application (version, last update)
- [x] Add `GET /api/system/info` (protected) returning structured JSON
- [x] Temperature warning threshold (70 °C); graceful degradation on non-Linux (e.g. macOS dev)

### Frontend
- [x] Add top-level tabs: **Dashboard** (Pi-hole), **System** (System Health + Updates)
- [x] Create `SystemHealthCard.jsx` — card-based sections (CPU, Memory, Temperature, Storage, Network, System, Application)
- [x] Mobile-first layout; status indicators (OK / warning / problem) for temperature and internet
- [x] Poll system info every 20 seconds; move Updates card under System tab and retitle to "Updates"

### Documentation
- [x] `architecture.md` — Navigation, System tab, System Health card, GET `/api/system/info`, project structure (system_info.py, SystemHealthCard.jsx)

---

## Phase 2.8: Morning Wake-up (Spotify Connect alarm)
> **Status: TODO**

Alarm at a set time: Pi plays a Spotify playlist over HDMI to the JBL soundbar. No dependency on PulseAudio/Snapcast; alarm is HDMI-only. Designed so future Phases 3–8 (music management) remain compatible.

### Backend
- [x] Add `state/alarm.json` — enabled, time (HH:MM), playlist_uri (optional)
- [x] Add `state/spotify.json` — refresh_token for Spotify Web API (user OAuth)
- [x] Create `alarm_manager.py` — load/save alarm config, background scheduler (check every minute), at alarm time call Spotify Web API: transfer playback to Pi device + start playlist
- [x] Create `spotify_auth.py` — OAuth: auth URL, callback (exchange code → tokens, save refresh_token), token refresh; Spotify Web API helpers (get devices, transfer playback, start playback)
- [x] Env: `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`; redirect URI via HTTPS
- [x] API: `GET /api/alarm`, `PUT /api/alarm` (body: enabled, time, playlist_uri); `GET /api/spotify/auth-url`, `GET /api/spotify/callback`, `GET /api/spotify/status`, `POST /api/spotify/disconnect`

### Caddy HTTPS (required for Spotify OAuth)
- [x] Install Caddy in `install_master.sh` (Let's Encrypt automatic cert)
- [x] Caddyfile: `SOUNDMAKER_DOMAIN { reverse_proxy 127.0.0.1:8081 }`
- [x] Move backend from port 80 to 8081 (Caddy proxies 443 → 8081; Pi-hole admin stays on 8080)
- [x] Spotify redirect URI via HTTPS: `https://DOMAIN/api/spotify/callback`
- [x] Add `SOUNDMAKER_DOMAIN` env var to install script (prompted if missing)
- [x] Update architecture.md communication model and network requirements

### Raspotify
- [x] Install `raspotify` in `install_master.sh` (Pi appears as "SoundMaker")
- [ ] Ensure default audio output is HDMI for alarm playback (JBL soundbar / ARC wake)

### Frontend — Wake-up section (Dashboard)
- [x] Alarm card: enable/disable toggle, time picker (HH:MM), optional playlist URI field, "Next alarm" summary
- [x] "Connect Spotify" flow: button opens auth URL; after callback, show "Spotify connected" and optional disconnect
- [x] Comfortable UX: clear labels, native time input, visible next alarm time, Spotify connection status

### Migration
- [x] Create `002_caddy_spotify_alarm.sh` — prints instructions to re-run install_master.sh for system-level changes

### Test
- [ ] Set alarm time and enable; connect Spotify via UI; at alarm time verify playlist starts on Pi (HDMI → soundbar)
- [ ] Disable alarm; verify no playback at that time

---

## Phase 2.9: Jellyfin Media Server
> **Status: DONE**

### Backend
- [x] Create `jellyfin_manager.py` — read-only status check (systemctl is-active)
- [x] Add API endpoint: `GET /api/jellyfin/status` (protected) — returns installed, running, url

### Frontend — Dashboard
- [x] Create `JellyfinCard.jsx` — status widget with link to Jellyfin web UI
- [x] Add to Dashboard tab in `App.jsx`

### Installation
- [x] Add Jellyfin installation section to `install_master.sh` (official Jellyfin Debian repo)
- [x] Create migration `005_jellyfin.sh` for existing deployments
- [x] Cap Jellyfin CPU in `install_master.sh` (systemd drop-in, Pi 5 thermal protection)
- [x] Create migration `006_jellyfin_cpu_limit.sh` for existing deployments
- [x] Disable Jellyfin by default (installed but not started/enabled) in `install_master.sh`
- [x] Create migration `007_disable_jellyfin.sh` for existing deployments

### Documentation
- [x] Update `README.md` — services table, Jellyfin setup section, network ports
- [x] Update `plan.md` — Phase 2.9
- [x] Update `architecture.md` — services table, Jellyfin section, thermal-protection / CPU-limit section

---

## Phase 2.10: Power controls, vitals history, log viewer
> **Status: DONE**

Three System-tab conveniences for a headless box: restart/reboot without SSH, a 24-hour vitals graph, and an in-UI journal log viewer.

### Backend
- [x] `power_manager.py` — restart backend / reboot Pi via `systemd-run --on-active=2` (transient timer survives the restart); weekly-reboot config (`state/power.json`) + minute scheduler
- [x] `metrics_history.py` — background sampler (1/min) of CPU temperature, CPU load, memory %, kept 24h in memory, persisted to `state/metrics_history.json` every ~5 min to limit SD-card wear
- [x] `system_logs.py` — read journald JSON for a whitelisted set of services (backend, Jellyfin, Pi-hole, Caddy, raspotify, Tailscale); service key never reaches the shell
- [x] API: `GET /api/system/metrics-history`, `GET /api/system/logs`, `GET /api/system/logs/services`, `POST /api/system/restart-service`, `POST /api/system/reboot`, `GET/PUT /api/system/auto-reboot`
- [x] Wire schedulers/sampler into app lifespan

### Frontend — System tab
- [x] `MetricsHistoryCard.jsx` — inline SVG line charts (temperature with 70 °C threshold line, CPU load, memory), no chart library
- [x] `LogsCard.jsx` — service dropdown, line-count selector, refresh + auto-refresh, entries colored by severity, newest in view
- [x] `PowerCard.jsx` — Restart backend + Reboot Pi buttons (with confirm), weekly-reboot schedule (day/time/on-off)

### Installation
- [x] `install_master.sh` → `install_power_permissions()` — add backend user to `systemd-journal`; write scoped `/etc/sudoers.d/soundmaker` (validated with `visudo -cf`)
- [x] Migration `008_power_controls_log_access.sh` for existing deployments

### Documentation
- [x] Update `README.md` (services/endpoints, System tab), `docs/architecture.md` (new section, endpoints, state, structure), `docs/plan.md`

---

## Phase 3: PulseAudio + Snapcast
> **Status: TODO**

### Master (Pi 5)
- [ ] Install PulseAudio on Master
- [ ] Configure pipe sink: `module-pipe-sink` writing to `/tmp/snapfifo` (s16le, 48000Hz)
- [ ] Set Snapcast as the default PulseAudio sink
- [ ] Install `snapserver` on Master
- [ ] Configure `snapserver` to read from `/tmp/snapfifo`
- [ ] Add PulseAudio + Snapcast to `install_master.sh`
- [ ] Verify Snapcast Server starts and listens on ports 1704/1705

### Slave (Pi Zero 2 W)
- [ ] Create `slave/install_slave.sh`
- [ ] Install `snapclient` on Slave
- [ ] Configure `snapclient` to connect to `soundmaker-master.local:1704`
- [ ] Configure ALSA/PulseAudio to output to USB DAC
- [ ] systemd service for snapclient
- [ ] Verify Slave auto-connects to Master

### End-to-end test
- [ ] Play a test audio file on Master through PulseAudio
- [ ] Confirm audio comes out of the Slave's speaker
- [ ] Confirm Snapcast Server reports the connected client

---

## Phase 4: Snapcast API + Room Management
> **Status: TODO**

### Backend
- [ ] Create `snapcast_api.py` — JSON-RPC client for Snapcast Server (port 1705)
- [ ] Implement: list clients, get status, set volume, mute/unmute
- [ ] Add API endpoints:
  - [ ] `GET /api/rooms` — list all Slaves with name, volume, muted, online status
  - [ ] `PUT /api/rooms/{id}/volume` — set volume (0–100)
  - [ ] `PUT /api/rooms/{id}/mute` — toggle mute
  - [ ] `PUT /api/rooms/{id}/name` — rename a Slave
- [ ] Detect new (unnamed) Slaves from Snapcast's `Server.GetStatus`
- [ ] Persist Slave names in `state/slaves.json`

### Frontend — Room Management section
- [ ] List all Slaves: name, online/offline status, volume slider, on/off toggle
- [ ] Unnamed Slaves appear at bottom for naming
- [ ] Real-time volume and mute control

### Test
- [ ] Control volume and mute from API and UI, verify audio changes on Slave
- [ ] Add a new Slave, confirm it appears unnamed in the UI, name it

---

## Phase 5: Internet Radio (mpv)
> **Status: TODO**

### Backend
- [ ] Install `mpv` on Master
- [ ] Create `radio_player.py` — manage `mpv` process (start, stop, restart with exponential backoff)
- [ ] Radio auto-starts on system boot (default source)
- [ ] Add API endpoints: `POST /api/radio/play`, `POST /api/radio/stop`, `GET /api/radio/status`
- [ ] Add stream URL endpoint: `PUT /api/config` to update `default_stream_url`
- [ ] Persist stream URL in `state/config.json`
- [ ] Add mpv install to `install_master.sh`

### Frontend — Dashboard source section
- [ ] Current source indicator (Radio / Spotify / Bluetooth) with visual distinction
- [ ] Play/stop button for radio
- [ ] Stream URL display and edit

### Test
- [ ] Radio plays through PulseAudio → Snapcast → Slave speaker
- [ ] Play/stop from the Web UI works
- [ ] Changing stream URL persists and takes effect

---

## Phase 6: Spotify Connect
> **Status: TODO**

### Backend
- [ ] Install `raspotify` (librespot) on Master
- [ ] Configure raspotify to output to PulseAudio
- [ ] Create `spotify_monitor.py` — monitor raspotify event hooks (play, stop, disconnect)
- [ ] Add Spotify install to `install_master.sh`
- [ ] Add API endpoint: `GET /api/source` — returns current active source

### Frontend
- [ ] Source indicator updates to "Spotify" when active
- [ ] Play/stop button disabled when Spotify is active

### Test
- [ ] Select "SoundMaker" from Spotify on phone, audio plays through all Slaves
- [ ] UI reflects Spotify as active source

---

## Phase 7: Bluetooth A2DP
> **Status: TODO**

### Backend
- [ ] Configure BlueZ as A2DP sink on Master
- [ ] Create `bluetooth_manager.py` — D-Bus control for BlueZ
  - [ ] Make Master discoverable (60s timeout)
  - [ ] Accept pairing automatically
  - [ ] Monitor connect/disconnect events
- [ ] Route Bluetooth audio through PulseAudio
- [ ] Persist paired devices in `state/bluetooth.json`
- [ ] Add API endpoints:
  - [ ] `POST /api/bluetooth/discover` — start 60s discoverable mode
  - [ ] `GET /api/bluetooth/devices` — list paired devices
  - [ ] `GET /api/bluetooth/status` — discoverable state, active connection
- [ ] Add BlueZ config to `install_master.sh`

### Frontend — Bluetooth section
- [ ] "Pair New Device" button with 60s countdown
- [ ] Paired devices list
- [ ] Source indicator updates to "Bluetooth" when active
- [ ] Play/stop button disabled when Bluetooth is active

### Test
- [ ] Pair phone, play audio, verify it comes out all Slaves
- [ ] UI reflects Bluetooth as active source

---

## Phase 8: Audio Source Manager
> **Status: TODO**

### Backend
- [ ] Create `audio_manager.py` — priority-based source switching
- [ ] Implement priority rules:
  - [ ] Spotify (1) overrides Bluetooth (2) overrides Radio (3)
  - [ ] On disconnect, cascade down to next available source
  - [ ] Radio resumes automatically when all higher sources disconnect
- [ ] Wire together: `spotify_monitor.py`, `bluetooth_manager.py`, `radio_player.py`
- [ ] Update `GET /api/source` to reflect real-time active source

### Frontend
- [ ] Source indicator and play/stop button respond correctly to all transitions

### Test
- [ ] Full priority chain: radio playing → connect BT (radio stops) → connect Spotify (BT stops) → disconnect Spotify (BT resumes) → disconnect BT (radio resumes)
- [ ] UI updates in real time through all transitions

---

## Phase 9: Deploy Script + Polish
> **Status: TODO**

- [ ] Create `deploy.sh` — SSH-based convenience script from dev machine
  - [ ] `./deploy.sh master` — git pull + optional install on Master
  - [ ] `./deploy.sh slave <hostname>` — git pull + optional install on Slave
- [ ] Verify all systemd services restart correctly on reboot
- [ ] Test failure scenarios (Slave disconnect, Master reboot, mpv crash, etc.)
- [ ] Final end-to-end walkthrough of all features
- [ ] Update `architecture.md` and `README.md` with final state
