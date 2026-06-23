# SoundMaker — Project Rules

## Everything must live in code (reproducible from scratch)

**Any change made on the Raspberry Pi must also be committed to this repo so a fresh Raspberry Pi 5 can be set up by running the install script — no manual, undocumented device tweaks.**

When you change something on the running Pi (a config file, a systemd unit, a package, a tuning value), you are not done until it is reproducible from the repo:

1. **Fresh installs** — add it to `master/install_master.sh` (the relevant `install_*` function), guarded to be idempotent (safe to re-run).
2. **Existing deployments** — add a numbered migration in `master/migrations/` (e.g. `00N_description.sh`) that applies the same change. Migrations run during an "Apply update".
3. **Docs** — update `README.md`, `docs/architecture.md`, and `docs/plan.md` to match.

A change that exists only on the device is considered incomplete: it will be lost on a reflash and is invisible to anyone reading the repo.

### Example

Capping Jellyfin's CPU to stop transcoding from overheating the Pi was done in all three places:
- `master/install_master.sh` → `install_jellyfin()` (writes the systemd drop-in)
- `master/migrations/006_jellyfin_cpu_limit.sh` (for existing installs)
- `README.md` + `docs/architecture.md` + `docs/plan.md`
