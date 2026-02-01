# Restarting FCT Stats Production Services

This prompt helps you restart the production FCT Stats website on the homelab server.

## Overview

The FCT Stats production site runs in Docker containers on a homelab server. There are different restart methods depending on whether you need a full rebuild or just want to restart existing containers.

## When to Restart

### Soft Restart (No Rebuild)
Use when:
- Database was updated (published with `publish-db.sh`)
- Minor configuration changes
- Services appear stuck but code hasn't changed
- After server reboot

### Hard Restart (With Rebuild)
Use when:
- Code was updated (published with `publish-webapp.sh`)
- Dependencies changed (requirements.txt)
- Dockerfile was modified
- Container is behaving unexpectedly

### Full Stop/Start
Use when:
- Need to completely reset containers
- Troubleshooting persistent issues
- Clearing all container state

## Restart Methods

### Method 1: Soft Restart (Fast, No Rebuild)
**Best for:** Database updates, quick restarts

```bash
cd ~/homelab/fct_stats
docker-compose -f docker/docker-compose.yml restart webapp
```

**What it does:**
- Stops the webapp container
- Starts it again with existing image
- Typically takes 5-10 seconds

### Method 2: Hard Restart (Rebuild Containers)
**Best for:** Code updates, dependency changes

**Option A: Using the script (recommended)**
```bash
./scripts/homelab-restart.sh
```

**Option B: Manual commands**
```bash
cd ~/homelab/fct_stats
docker-compose -f docker/docker-compose.yml down
docker-compose -f docker/docker-compose.yml up -d --build
```

**What it does:**
1. Stops and removes containers
2. Rebuilds webapp image from Dockerfile
3. Starts new containers with fresh build
4. Takes 30-60 seconds

### Method 3: Full Stop/Start
**Best for:** Troubleshooting, clearing state

**Stop services:**
```bash
./scripts/homelab-stop.sh
# Or manually:
cd ~/homelab/fct_stats
docker-compose -f docker/docker-compose.yml down
```

**Start services:**
```bash
./scripts/homelab-start.sh
# Or manually:
cd ~/homelab/fct_stats
docker-compose -f docker/docker-compose.yml up -d
```

## Step-by-Step Restart Workflows

### Scenario 1: Just Published New Database

1. **Database was published:**
   ```bash
   ./scripts/publish-db.sh
   ```

2. **Soft restart webapp:**
   ```bash
   cd ~/homelab/fct_stats
   docker-compose -f docker/docker-compose.yml restart webapp
   ```

3. **Verify:**
   ```bash
   docker-compose -f docker/docker-compose.yml logs -f webapp
   # Press Ctrl+C to exit logs
   ```

4. **Check site:**
   - Visit http://fct-stats.duckdns.org
   - Verify new data is visible

### Scenario 2: Published Code Changes

1. **Webapp was published:**
   ```bash
   ./scripts/publish-webapp.sh
   ```

2. **Hard restart with rebuild:**
   ```bash
   ./scripts/homelab-restart.sh
   ```

3. **Monitor logs during startup:**
   ```bash
   cd ~/homelab/fct_stats
   docker-compose -f docker/docker-compose.yml logs -f webapp
   ```

4. **Verify:**
   - Check logs for errors
   - Visit http://fct-stats.duckdns.org
   - Test new functionality

### Scenario 3: Site is Down/Not Responding

1. **Check if containers are running:**
   ```bash
   cd ~/homelab/fct_stats
   docker-compose -f docker/docker-compose.yml ps
   ```

2. **If not running, start them:**
   ```bash
   ./scripts/homelab-start.sh
   ```

3. **If running but not responding:**
   ```bash
   ./scripts/homelab-restart.sh
   ```

4. **Check logs for errors:**
   ```bash
   docker-compose -f docker/docker-compose.yml logs -f webapp
   ```

### Scenario 4: After Server Reboot

1. **Navigate to homelab directory:**
   ```bash
   cd ~/homelab/fct_stats
   ```

2. **Check if services auto-started:**
   ```bash
   docker-compose -f docker/docker-compose.yml ps
   ```

3. **If not running, start them:**
   ```bash
   docker-compose -f docker/docker-compose.yml up -d
   ```

4. **Verify:**
   ```bash
   docker-compose -f docker/docker-compose.yml ps
   docker-compose -f docker/docker-compose.yml logs webapp
   ```

## Useful Commands

### Check Container Status
```bash
cd ~/homelab/fct_stats
docker-compose -f docker/docker-compose.yml ps
```

**Expected output:**
```
NAME                IMAGE              STATUS       PORTS
fct_stats_webapp    fct_stats-webapp   Up 5 minutes   5000/tcp
```

### View Live Logs
```bash
cd ~/homelab/fct_stats
docker-compose -f docker/docker-compose.yml logs -f webapp
# Press Ctrl+C to exit
```

### View Last 50 Log Lines
```bash
docker-compose -f docker/docker-compose.yml logs --tail=50 webapp
```

### Execute Command in Container
```bash
docker-compose -f docker/docker-compose.yml exec webapp /bin/bash
# Or check Python version:
docker-compose -f docker/docker-compose.yml exec webapp python --version
```

### Check Database in Container
```bash
docker-compose -f docker/docker-compose.yml exec webapp sqlite3 /app/data/fct_stats.db "SELECT COUNT(*) FROM athletes;"
```

### Force Remove Everything and Rebuild
```bash
cd ~/homelab/fct_stats
docker-compose -f docker/docker-compose.yml down -v
docker-compose -f docker/docker-compose.yml up -d --build
```

## Troubleshooting

### Container Keeps Restarting

1. **Check logs for errors:**
   ```bash
   docker-compose -f docker/docker-compose.yml logs webapp
   ```

2. **Common issues:**
   - Database file not found: Run `./scripts/publish-db.sh`
   - Port conflict: Check if another service is using port 5000
   - Python dependencies: Rebuild with `--build` flag

### "Network proxy-network not found"

The webapp needs the nginx proxy network. Create it:
```bash
docker network create proxy-network
```

Then restart:
```bash
docker-compose -f docker/docker-compose.yml up -d
```

### Changes Not Visible After Restart

1. **Clear browser cache:**
   - Chrome/Firefox: Ctrl+Shift+R (hard reload)
   - Or use incognito/private window

2. **Verify file was published:**
   ```bash
   ls -lh ~/homelab/fct_stats/webapp/templates/
   cat ~/homelab/fct_stats/webapp/app.py | grep "def index"
   ```

3. **Rebuild container:**
   ```bash
   docker-compose -f docker/docker-compose.yml up -d --build
   ```

### Database Shows Old Data

1. **Check database timestamp:**
   ```bash
   ls -lh ~/homelab/fct_stats/data/fct_stats.db
   ```

2. **Verify database content:**
   ```bash
   sqlite3 ~/homelab/fct_stats/data/fct_stats.db "SELECT name, date FROM meets ORDER BY date DESC LIMIT 5;"
   ```

3. **Re-publish database:**
   ```bash
   ./scripts/publish-db.sh
   cd ~/homelab/fct_stats
   docker-compose -f docker/docker-compose.yml restart webapp
   ```

### Container Won't Start

1. **Check Docker daemon:**
   ```bash
   systemctl status docker
   ```

2. **Check for resource issues:**
   ```bash
   docker system df
   docker system prune  # Clean up unused resources
   ```

3. **View detailed logs:**
   ```bash
   docker logs fct_stats_webapp
   ```

## Production Environment Details

### Container Configuration
- **Container Name**: `fct_stats_webapp`
- **Base Image**: Built from `docker/Dockerfile.webapp`
- **Exposed Port**: 5000 (internal)
- **Restart Policy**: `unless-stopped` (auto-restarts on failure)

### Mounted Volumes
- **Database**: `../data:/app/data:ro` (read-only)
  - Host: `~/homelab/fct_stats/data/fct_stats.db`
  - Container: `/app/data/fct_stats.db`

### Environment Variables
- `DATABASE_PATH=/app/data/fct_stats.db`
- `CONFIG_PATH=/app/config`
- `VIRTUAL_HOST=fct-stats.duckdns.org`
- `LETSENCRYPT_HOST=fct-stats.duckdns.org`

### Network
- **Network**: `proxy-network` (external)
- **Purpose**: Connects to nginx reverse proxy for HTTPS

## Quick Reference

### Most Common Restart Scenarios

| Scenario | Command |
|----------|---------|
| Published new database | `docker-compose -f docker/docker-compose.yml restart webapp` |
| Published code changes | `./scripts/homelab-restart.sh` |
| Site is down | `./scripts/homelab-start.sh` |
| Need fresh start | `./scripts/homelab-stop.sh` then `./scripts/homelab-start.sh` |
| After server reboot | `cd ~/homelab/fct_stats && docker-compose -f docker/docker-compose.yml up -d` |

### Scripts Available

| Script | Purpose |
|--------|---------|
| `./scripts/homelab-start.sh` | Start services (no rebuild) |
| `./scripts/homelab-stop.sh` | Stop all services |
| `./scripts/homelab-restart.sh` | Stop, rebuild, and start |

## Pre-Restart Checklist

- [ ] Know why you're restarting (code change, data update, troubleshooting)
- [ ] Recent changes published (if applicable)
- [ ] Have checked logs for current issues
- [ ] Chosen appropriate restart method

## Post-Restart Verification

- [ ] Container status shows "Up": `docker-compose ps`
- [ ] No errors in logs: `docker-compose logs webapp`
- [ ] Site accessible: http://fct-stats.duckdns.org
- [ ] Expected changes visible
- [ ] No console errors in browser (F12 developer tools)

## Emergency Commands

### Site is completely broken
```bash
cd ~/homelab/fct_stats
docker-compose -f docker/docker-compose.yml down -v
./scripts/publish-all.sh
docker-compose -f docker/docker-compose.yml up -d --build
```

### Restore from backup
```bash
# List backups
ls -lh ~/homelab/fct_stats/backups/

# Copy backup to production
cp ~/homelab/fct_stats/backups/fct_stats_YYYYMMDD_HHMMSS.db ~/homelab/fct_stats/data/fct_stats.db

# Restart
docker-compose -f docker/docker-compose.yml restart webapp
```
