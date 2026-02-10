# Publishing FCT Stats to Production

This prompt helps you publish the FCT Stats application to the homelab production server.
model: GPT-4o (copilot)

## Overview

The FCT Stats application runs on a homelab server using Docker containers. There are separate publish scripts for:
- **Webapp**: Flask application code, templates, static files
- **Database**: SQLite database with all athlete/meet/result data
- **Both**: Combined publish (recommended for most updates)

## Quick Start (Default Command)

To publish everything and restart the production server in one go:

```bash
./scripts/publish-all.sh && cd ~/homelab/fct_stats && mkdir -p data/generated/db && mv data/fct_stats.db data/generated/db/fct_stats.db 2>/dev/null || true && docker-compose -f docker/docker-compose.yml up -d --build
```

Or create an alias in your shell:
```bash
alias publish-prod='./scripts/publish-all.sh && cd ~/homelab/fct_stats && mkdir -p data/generated/db && mv data/fct_stats.db data/generated/db/fct_stats.db 2>/dev/null || true && docker-compose -f docker/docker-compose.yml up -d --build'
```

Then just run: `publish-prod`

---

## Publishing Options

### Option 1: Publish Everything (Recommended)
Use this when you've made changes to both code and data.

```bash
./scripts/publish-all.sh
```

**What it does:**
1. Syncs webapp code to `~/homelab/fct_stats/` (excluding development files)
2. Backs up existing database to `~/homelab/fct_stats/backups/`
3. Copies new database from `data/generated/db/fct_stats.db` to homelab
4. Shows database statistics

**Then restart the server:**
```bash
cd ~/homelab/fct_stats
mkdir -p data/generated/db
mv data/fct_stats.db data/generated/db/fct_stats.db 2>/dev/null || true
docker-compose -f docker/docker-compose.yml up -d --build
```

**Or use the restart script:**
```bash
./scripts/homelab-restart.sh
```

### Option 2: Publish Only Webapp
Use this when you've made code/template/styling changes but no database changes.

```bash
./scripts/publish-webapp.sh
```

**What it does:**
- Syncs webapp files using rsync
- Excludes: venv, __pycache__, .git, data/generated/db/, data/sources/current/pages/, data/sources/current/meets/

**Then restart the webapp container:**
```bash
./scripts/homelab-restart.sh
```

Or manually:
```bash
cd ~/homelab/fct_stats
docker-compose -f docker/docker-compose.yml restart webapp
```

### Option 3: Publish Only Database
Use this when you've added new meet results or updated data but code is unchanged.

```bash
./scripts/publish-db.sh
```

**What it does:**
1. Creates backup: `~/homelab/fct_stats/backups/fct_stats_YYYYMMDD_HHMMSS.db`
2. Copies `data/generated/db/fct_stats.db` to `~/homelab/fct_stats/data/generated/db/`
3. Shows statistics (athletes, events, meets, results counts)

**Then restart the webapp container:**
```bash
./scripts/homelab-restart.sh
```

Or manually:
```bash
cd ~/homelab/fct_stats
docker-compose -f docker/docker-compose.yml restart webapp
```

### Option 4: Just Restart the Production Server
Use this to restart the server without publishing any changes.

```bash
./scripts/homelab-restart.sh
```

**What it does:**
1. Stops existing services
2. Rebuilds and starts fresh containers
3. Shows confirmation

Or manually:
```bash
cd ~/homelab/fct_stats
docker-compose -f docker/docker-compose.yml down
docker-compose -f docker/docker-compose.yml up -d --build
```

## Step-by-Step Publishing Workflow

### For a Typical Update (New Meet Results Added)

1. **Ensure database is up to date:**
   ```bash
   python scripts/import_from_parsed_meets.py
   ```

2. **Verify locally:**
   ```bash
   cd webapp
   python app.py
   # Visit http://localhost:5000 and check changes
   ```

3. **Publish everything:**
   ```bash
   ./scripts/publish-all.sh
   ```

4. **Restart production services:**
   ```bash
   cd ~/homelab/fct_stats
   docker-compose -f docker/docker-compose.yml up -d --build
   ```

5. **Check logs for errors:**
   ```bash
   docker-compose -f docker/docker-compose.yml logs -f webapp
   ```

6. **Visit production site:**
   - http://fct-stats.duckdns.org

### For Code-Only Changes (Templates, Styling, Routes)

1. **Test locally:**
   ```bash
   cd webapp
   python app.py
   ```

2. **Publish webapp only:**
   ```bash
   ./scripts/publish-webapp.sh
   ```

3. **Restart webapp container:**
   ```bash
   cd ~/homelab/fct_stats
   docker-compose -f docker/docker-compose.yml restart webapp
   ```

### For Data-Only Changes (New Results, Updated Records)

1. **Import new data:**
   ```bash
   python scripts/import_from_parsed_meets.py
   ```

2. **Publish database only:**
   ```bash
   ./scripts/publish-db.sh
   ```

3. **Restart webapp container:**
   ```bash
   cd ~/homelab/fct_stats
   docker-compose -f docker/docker-compose.yml restart webapp
   ```

## Important Notes

### Database Backups
- Automatic backups are created in `~/homelab/fct_stats/backups/`
- Format: `fct_stats_YYYYMMDD_HHMMSS.db`
- **These backups are important!** The database is read-only in production

### What Gets Excluded During Webapp Sync
The rsync excludes:
- `venv/` - Virtual environments
- `__pycache__/` - Python bytecode
- `*.pyc` - Compiled Python files
- `.git/` - Git repository
- `data/generated/db/` - Database (published separately)
- `data/sources/current/pages/` - Raw meet pages (not needed in production)
- `data/sources/current/meets/` - YAML meet files (not needed in production)
- `.vscode/` - Editor config
- `*.log` - Log files

### Production Environment
- **Location**: `~/homelab/fct_stats/`
- **Docker Compose**: `docker/docker-compose.yml`
- **URL**: http://fct-stats.duckdns.org
- **Container Name**: `fct_stats_webapp`
- **Network**: `proxy-network` (shared with nginx proxy)
- **Database**: Mounted read-only from `../data/generated/db/fct_stats.db`

## Troubleshooting

### Site Not Updating After Publish

1. **Check if services are running:**
   ```bash
   cd ~/homelab/fct_stats
   docker-compose -f docker/docker-compose.yml ps
   ```

2. **Rebuild containers:**
   ```bash
   docker-compose -f docker/docker-compose.yml up -d --build
   ```

3. **Check logs:**
   ```bash
   docker-compose -f docker/docker-compose.yml logs -f webapp
   ```

### Database Not Found Error

1. **Verify database is in correct location:**
   ```bash
   ls -lh ~/homelab/fct_stats/data/generated/db/fct_stats.db
   ```
   
   If the database is at `~/homelab/fct_stats/data/fct_stats.db`, move it:
   ```bash
   mkdir -p ~/homelab/fct_stats/data/generated/db
   mv ~/homelab/fct_stats/data/fct_stats.db ~/homelab/fct_stats/data/generated/db/fct_stats.db
   ```

2. **Check database permissions:**
   ```bash
   chmod 644 ~/homelab/fct_stats/data/generated/db/fct_stats.db
   ```

3. **Verify database is valid:**
   ```bash
   sqlite3 ~/homelab/fct_stats/data/generated/db/fct_stats.db "SELECT COUNT(*) FROM athletes;"
   ```

4. **Restart the container:**
   ```bash
   cd ~/homelab/fct_stats
   docker-compose -f docker/docker-compose.yml restart webapp
   ```

### Container Won't Start

1. **Check for port conflicts:**
   ```bash
   docker-compose -f docker/docker-compose.yml ps
   netstat -tulpn | grep 5000
   ```

2. **Remove old containers:**
   ```bash
   docker-compose -f docker/docker-compose.yml down
   docker-compose -f docker/docker-compose.yml up -d
   ```

3. **Check Docker logs:**
   ```bash
   docker logs fct_stats_webapp
   ```

## Quick Reference Commands

```bash
# QUICK START: Publish everything and restart (recommended)
./scripts/publish-all.sh && cd ~/homelab/fct_stats && mkdir -p data/generated/db && mv data/fct_stats.db data/generated/db/fct_stats.db 2>/dev/null || true && docker-compose -f docker/docker-compose.yml up -d --build

# Or use the dedicated script
./scripts/homelab-restart.sh

# Publish everything only (without restart)
./scripts/publish-all.sh

# Publish webapp only
./scripts/publish-webapp.sh

# Publish database only
./scripts/publish-db.sh

# Restart services (after publishing separately)
./scripts/homelab-restart.sh

# Manual restart without publish
cd ~/homelab/fct_stats
docker-compose -f docker/docker-compose.yml up -d --build

# Restart just the webapp container
docker-compose -f docker/docker-compose.yml restart webapp

# Stop services
docker-compose -f docker/docker-compose.yml down

# View logs
docker-compose -f docker/docker-compose.yml logs -f

# Check status
docker-compose -f docker/docker-compose.yml ps
```

## Pre-Publish Checklist

- [ ] Local changes tested with `cd webapp && python app.py`
- [ ] Database imported with latest data: `python scripts/import_from_parsed_meets.py`
- [ ] No errors in local testing
- [ ] Git committed (optional but recommended)
- [ ] Ready to run appropriate publish script

## Post-Publish Verification

- [ ] Services started: `docker-compose ps` shows "Up"
- [ ] No errors in logs: `docker-compose logs webapp`
- [ ] Production site accessible: http://fct-stats.duckdns.org
- [ ] New data/changes visible on production site
- [ ] Database backup created (if db was published)
