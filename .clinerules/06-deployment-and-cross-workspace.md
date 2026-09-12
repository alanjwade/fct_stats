# Deployment, Versioning & cross-workspace relationship

Two repos work together. Keep the split clean:

- **`fct_stats` (this repo)** — app source of truth. All code lives here.
- **`homelab-infra`** (sibling workspace) — the only place that knows anything
  about where/what the app runs on.

## The split

- **This repo's only job is to ship a container image.** On a `v*` release tag,
  `.github/workflows/build-push.yml` builds and publishes
  `ghcr.io/alanjwade/fct-stats:<tag>`. It does not touch, notify, or know
  anything about a host, a compose file, a deploy path, or a machine.
- **homelab-infra owns all deployment.** The pinned image tag, the compose
  file, the host, and the up-to-date check live in
  `homelab-infra/hosts/homelab01/fct-stats/`. A general-purpose script there
  (`homelab-infra/scripts/update-apps.sh`) watches GHCR, bumps the pinned tag,
  commits/pushes, then sshs into the host to `git pull` + `docker compose pull`
  + `docker compose up -d`. homelab-infra discovers this app because that
  service folder carries an `app.yml` manifest.

## Release flow

1. **Create & push the release tag (local).** `bump_release.sh` is the single
   command to ship a release (requires a clean tree). It reads the newest
   `vX.Y.Z` tag, computes the next version (patch by default; `minor`/`major`
   accepted), pushes the branch HEAD, and creates/pushes the new tag:
   ```bash
   ./bump_release.sh          # v0.0.1 -> v0.0.2
   ./bump_release.sh minor    # v0.0.1 -> v0.1.0
   ```
   It is **target-agnostic** — no file edits, and it knows nothing about the
   deployment host.

2. **CI publishes the image only (GitHub):** `build-push.yml` builds and pushes
   `ghcr.io/alanjwade/fct-stats:<tag>`, passing `APP_VERSION=<tag>` as a build
   arg.

3. **The tag appears in the webapp footer.** The Dockerfile stores the
   build-time `APP_VERSION` as a runtime env var; `app.py` exposes it via
   `app.context_processor` and `base.html` renders it. Locally (no Docker) it
   falls back to `dev`.

4. **homelab-infra deploys it:**
   ```bash
   cd homelab-infra && ./scripts/update-apps.sh fct-stats
   ```

## Data / backups

- The SQLite database lives on the host at
  `/opt/homelab/fct-stats/data/db/fct_stats.db`. It is generated here (scraper)
  and shipped by `homelab-infra/scripts/update-db.sh`, which reads the `data:`
  block in `homelab-infra/hosts/homelab01/fct-stats/app.yml`.
- The analytics DB lives at `/opt/homelab/fct-stats/analytics/analytics.db`
  (generated at runtime on the host).
- Config (`config/*.yaml`, `config/*.json`) is **baked into the image** at build
  time. Change it here and cut a release; there is no config mount.

## Environment

- Never hardcode machine-specific secrets. `ANALYTICS_SECRET` / `VISITOR_SALT`
  have defaults in `app.py`; override them via the host's `.env`.
