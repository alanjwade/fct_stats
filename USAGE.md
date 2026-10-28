# FCT Stats - Usage Guide

Track statistics website for the Fort Collins High School track team.

## Architecture Overview

- **Scraper**: Python scripts that parse meet results from HTML pages and populate the SQLite database
- **Database**: SQLite database (`data/generated/db/fct_stats.db`) storing athletes, meets, events, and results
- **Webapp**: Flask web application displaying statistics and records
- **Deployment**: release-tracked container image (`ghcr.io/alanjwade/fct-stats`) built by CI and deployed by `homelab-infra` — see "Publishing" below

---

## Development Workflow

### 1. Running the Scraper

The scraper processes meet results from HTML files and populates the database.

#### One-Time Setup

Create a Python virtual environment in the scraper directory:

```bash
cd scraper
python -m venv venv
source venv/bin/activate  # On Linux/Mac
pip install -r requirements.txt
deactivate  # Exit venv for now
cd ..
```

#### Add a New Meet

1. **Save the HTML page**: Download the meet results page and save to `data/sources/current/pages/YYYY/`
   ```bash
   mkdir -p data/sources/current/pages/2025
   # Save HTML file, e.g., "Longmont Invitational 2025.html"
   ```

2. **Create meet configuration**: Create a YAML file in `data/sources/current/meets/YYYY/`
   ```bash
   cd data/sources/current/meets/2025
   nano longmont_invitational_2025.yaml
   ```

   Example configuration:
   ```yaml
   name: "Longmont Invitational"
   date: "2025-03-15"
   season: "2025"
   level: "varsity"  # or "jv" or "open"
   sources:
     - file: "pages/2025/Longmont Invitational 2025.html"
       parser: "auto"  # Auto-detect parser type
   ```

#### Run the scraper:

Always start from the project root directory:

```bash
cd /home/alan/Documents/code/fct_stats
source scraper/venv/bin/activate
python -m scraper.scraper data/sources/current/meets/2025/longmont_invitational_2025.yaml
deactivate  # Exit venv when done
```

#### Scraper Options

Clear database before scraping:

```bash
# Clear only results (keeps athletes, events, meets)
python -m scraper.scraper --clear-results data/sources/current/meets/2025/meet.yaml

# Clear all meets and results (keeps athletes and events)
python -m scraper.scraper --clear-meets data/sources/current/meets/2025/meet.yaml

# Clear entire database (fresh start)
python -m scraper.scraper --clear-all data/sources/current/meets/2025/meet.yaml
```

Scraping modes:

```bash
# Scrape specific meet file
python -m scraper.scraper data/meets/2025/meet.yaml

# Scrape all meets in a directory (searches recursively)
python -m scraper.scraper --meet-dir data/sources/current/meets/2025

# Scrape all meets in default data/sources/current/meets/ directory
python -m scraper.scraper

# Use custom database path
python -m scraper.scraper --db /path/to/database.db data/sources/current/meets/2025/meet.yaml
```

Combined examples:

```bash
# Clear results and scrape a specific meet
python -m scraper.scraper --clear-results data/meets/2025/meet.yaml

# Clear results and scrape entire year
python -m scraper.scraper --meet-dir data/sources/current/meets/2025 --clear-results

# Clear all data and rebuild from scratch
python -m scraper.scraper --meet-dir data/sources/current/meets/2025 --clear-all
```

**Important**: Always activate the virtual environment first:
```bash
source scraper/venv/bin/activate
python -m scraper.scraper [options] [meet.yaml]
deactivate
```

#### Scraper Output

The scraper will:
- Parse the HTML results page
- Match events to canonical event names (from `config/canonical_events.yaml`)
- Match schools to Fort Collins athletes
- Create/update athlete records
- Insert results into the database

Check the output for:
- Number of results processed
- Any matching warnings or errors
- Database insertions confirmed

---

### Clearing the Database

You can clear the database before scraping to ensure clean data:

```bash
# Delete all results but keep athletes, events, and meets
python -m scraper.scraper --clear-results data/meets/2025/meet.yaml

# Delete all meets and results (keeps athletes and events for reference)
python -m scraper.scraper --clear-meets data/meets/2025/meet.yaml

# Delete everything - start completely fresh
python -m scraper.scraper --clear-all data/meets/2025/meet.yaml
```

This is useful when re-parsing a meet that had parsing errors, or when starting fresh with new data.

---

### 2. Running the Webapp Locally

For development and testing:

```bash
cd webapp
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run development server
python app.py
```

The webapp will be available at `http://localhost:5000`

#### Restarting the Webapp

If you've made changes to templates or code:

```bash
# Stop the running process (Ctrl+C)
# Restart
python app.py
```

For Docker development:
```bash
cd docker
docker-compose -f docker-compose.dev.yml down
docker-compose -f docker-compose.dev.yml up --build
```

---

### 3. Building Images

The **production image is built by CI, not locally**: `.github/workflows/build-push.yml`
builds `Dockerfile` and publishes `ghcr.io/alanjwade/fct-stats:<tag>` on every `v*`
release tag. `docker/Dockerfile.webapp` and `docker/Dockerfile.scraper` are
development-only.

```bash
# The same image CI ships (production):
docker build -t fct-stats:local .

# Development images:
docker build -f docker/Dockerfile.webapp -t fct-stats:webapp-dev .
docker build -f docker/Dockerfile.scraper -t fct-stats:scraper-dev .
```

To run the *published* image without homelab-infra:

```bash
docker compose -f docker-compose.ghcr.yml pull
docker compose -f docker-compose.ghcr.yml up -d
```

---

## Publishing

This repo ships a container image; **deployment is owned by `homelab-infra`**
(`hosts/homelab01/fct-stats/`). There is no publish script here — the commands
below are the whole flow.

### 4. Publishing the Webapp (code, templates, config)

1. Commit your change — `bump_release.sh` requires a clean tree.
2. Cut a release tag; CI builds and pushes the image:

   ```bash
   ./bump_release.sh          # patch; also accepts: minor | major
   ```

3. Deploy that tag from the `homelab-infra` checkout:

   ```bash
   cd ../homelab-infra
   ./scripts/update-apps.sh --check        # optional: report only
   ./scripts/update-apps.sh fct-stats      # bump pin, push, ssh homelab01, pull + up -d
   ```

`update-apps.sh` rewrites the pinned tag in
`hosts/homelab01/fct-stats/docker-compose.yml`, commits + pushes that repo, then
sshs to `homelab01` to `git pull` and `docker compose pull` / `up -d`. If CI has
not published the tag yet it reports "up to date" — rerun it, or use
`./scripts/update-apps.sh fct-stats --deploy-only` to redeploy the already-pinned
tag without a version bump.

### 5. Publishing the Database

The SQLite db is generated here by the scraper and shipped by `homelab-infra`
(the `data:` block in `hosts/homelab01/fct-stats/app.yml` names the local source
and the remote destination):

```bash
cd ../homelab-infra
./scripts/update-db.sh fct-stats
```

That snapshots the current remote db (timestamped `.bak`), uploads to a temp
name, `mv`s it into place at `/opt/homelab/fct-stats/data/db/fct_stats.db`, then
restarts the container (a long-lived gunicorn worker would otherwise keep
reading the old inode).

### 6. Verifying a Publish

```bash
curl -I https://track.fchsrunning.org                # Cloudflare → caddy → fct-stats:5000
ssh homelab01 'docker ps --filter name=fct-stats'    # image tag + uptime
ssh homelab01 'docker logs --tail 50 fct-stats'
```

### 7. Backups

Handled by `homelab-infra`'s backup runners from
`hosts/homelab01/fct-stats/backup.yml` (`local` + `offsite` tiers cover
`/opt/homelab/fct-stats/data` and `.../analytics`) — there is no per-service
backup script here.

---

## Configuration Files

### Event Configuration

Edit `config/canonical_events.yaml` to add/remove events:

```yaml
Track:
  - "100m"
  - "200m"
  # ... other events
```

Events not in this list will be logged as unmatched during scraping.

### School Configuration

Edit `config/schools.yaml` to configure school matching:

```yaml
fort_collins:
  - "Fort Collins"
  - "Fort Collins HS"
  - "FC"
  - "FCHS"
```

---

## Common Tasks

### Add a New Event

1. Edit `config/canonical_events.yaml`
2. Re-run scraper on affected meets
3. Event will auto-populate in database

### Fix Athlete Names

```bash
sqlite3 data/fct_stats.db
UPDATE athletes SET first_name = 'John', last_name = 'Doe' WHERE id = 123;
.quit
```

### Delete a Meet

```bash
sqlite3 data/fct_stats.db
DELETE FROM results WHERE meet_id = (SELECT id FROM meets WHERE name = 'Meet Name');
DELETE FROM meets WHERE name = 'Meet Name';
.quit
```

### View Recent Results

```bash
sqlite3 data/fct_stats.db << EOF
SELECT 
  a.first_name || ' ' || a.last_name as athlete,
  e.name as event,
  r.mark_display,
  m.name as meet
FROM results r
JOIN athletes a ON r.athlete_id = a.id
JOIN events e ON r.event_id = e.id
JOIN meets m ON r.meet_id = m.id
ORDER BY m.meet_date DESC
LIMIT 20;
EOF
```

---

## Troubleshooting

### Scraper Issues

**Problem**: Events not matching
- Check `config/canonical_events.yaml` for event name
- Look at scraper output for "Unmatched event" warnings
- HTML parser may need adjustment

**Problem**: Athletes not being created
- Check `config/schools.yaml` for school name variations
- Verify HTML page has Fort Collins results

### Webapp Issues

**Problem**: No data showing
- Verify database exists: `ls -lh data/generated/db/fct_stats.db`
- Check database has data: `sqlite3 data/generated/db/fct_stats.db "SELECT COUNT(*) FROM results;"`
- Check Flask logs for errors

**Problem**: Docker container won't start
- Check logs: `docker-compose logs webapp`
- Verify port 80 is not in use: `sudo netstat -tlnp | grep :80`
- Check database file permissions

### Database Issues

**Problem**: Database locked
- Stop all connections to database
- If using Docker: `docker-compose restart webapp`

**Problem**: Corrupted database
- Restore from backup
- If no backup, check integrity: `sqlite3 data/generated/db/fct_stats.db "PRAGMA integrity_check;"`

---

## Project Structure

```
fct_stats/
├── config/              # Configuration files
│   ├── canonical_events.yaml
│   └── schools.yaml
├── data/
│   ├── sources/                    # Source data (input files)
│   │   ├── current/
│   │   │   ├── 2025/              # Current year spreadsheets and configs
│   │   │   ├── pages/             # Downloaded HTML/TXT results
│   │   │   └── meets/             # Meet configuration YAMLs
│   │   └── historic/              # Historical records (markdown)
│   └── generated/                  # Generated output (regenerable)
│       ├── db/
│       │   └── fct_stats.db       # SQLite database
│       └── parsed/                 # Parsed JSON results
│           ├── meets/             # Individual meet results
│           ├── historical_records.json
│           └── parsed_performance_list.json
├── database/
│   └── schema.sql      # Database schema
├── docker/             # Development-only Docker configs
│   ├── docker-compose.dev.yml
│   ├── Dockerfile.webapp
│   └── Dockerfile.scraper
├── scraper/            # Data scraping scripts
│   ├── scraper.py
│   ├── database.py
│   └── parsers/
├── webapp/             # Flask web application
│   ├── app.py
│   ├── templates/
│   └── static/
└── USAGE.md           # This file
```

---

## Support

For issues or questions about the codebase, check:
- Database schema: `database/schema.sql`
- Parser implementations: `scraper/parsers/`
- Template structure: `webapp/templates/`

Last updated: December 18, 2025
