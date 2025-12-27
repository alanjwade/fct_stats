# FCT Stats - Usage Guide

Track statistics website for the Fort Collins High School track team.

## Architecture Overview

- **Scraper**: Python scripts that parse meet results from HTML pages and populate the SQLite database
- **Database**: SQLite database (`data/fct_stats.db`) storing athletes, meets, events, and results
- **Webapp**: Flask web application displaying statistics and records
- **Deployment**: Docker containers with nginx reverse proxy for production

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

1. **Save the HTML page**: Download the meet results page and save to `data/pages/YYYY/`
   ```bash
   mkdir -p data/pages/2025
   # Save HTML file, e.g., "Longmont Invitational 2025.html"
   ```

2. **Create meet configuration**: Create a YAML file in `data/meets/YYYY/`
   ```bash
   cd data/meets/2025
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
python -m scraper.scraper data/meets/2025/longmont_invitational_2025.yaml
deactivate  # Exit venv when done
```

#### Scraper Options

Clear database before scraping:

```bash
# Clear only results (keeps athletes, events, meets)
python -m scraper.scraper --clear-results data/meets/2025/meet.yaml

# Clear all meets and results (keeps athletes and events)
python -m scraper.scraper --clear-meets data/meets/2025/meet.yaml

# Clear entire database (fresh start)
python -m scraper.scraper --clear-all data/meets/2025/meet.yaml
```

Scraping modes:

```bash
# Scrape specific meet file
python -m scraper.scraper data/meets/2025/meet.yaml

# Scrape all meets in a directory (searches recursively)
python -m scraper.scraper --meet-dir data/meets/2025

# Scrape all meets in default data/meets/ directory
python -m scraper.scraper

# Use custom database path
python -m scraper.scraper --db /path/to/database.db data/meets/2025/meet.yaml
```

Combined examples:

```bash
# Clear results and scrape a specific meet
python -m scraper.scraper --clear-results data/meets/2025/meet.yaml

# Clear results and scrape entire year
python -m scraper.scraper --meet-dir data/meets/2025 --clear-results

# Clear all data and rebuild from scratch
python -m scraper.scraper --meet-dir data/meets/2025 --clear-all
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

### 3. Building for Production

#### Build Docker Images

```bash
cd docker

# Build both webapp and scraper images
docker-compose build

# Or build individually
docker build -f Dockerfile.webapp -t fct_stats_webapp ..
docker build -f Dockerfile.scraper -t fct_stats_scraper ..
```

#### Test Production Build Locally

```bash
cd docker
docker-compose up
```

Access the site at `http://localhost:80`

---

## Homelab Deployment

### 4. Publishing to Homelab

For running on your local homelab at `~/homelab/fct_stats`:

#### Quick Publish (Webapp + Database)

```bash
# Publish everything to homelab
./scripts/publish-all.sh

# Start the services
./scripts/homelab-start.sh
```

The site will be available at `http://localhost:80`

#### Individual Publishing

Publish just the webapp (code updates):
```bash
./scripts/publish-webapp.sh
./scripts/homelab-restart.sh  # Rebuild and restart
```

Publish just the database (after scraping new data):
```bash
./scripts/publish-db.sh
```

#### Managing Homelab Services

```bash
# Start services
./scripts/homelab-start.sh

# Stop services
./scripts/homelab-stop.sh

# Restart with rebuild (after code changes)
./scripts/homelab-restart.sh

# View logs
cd ~/homelab/fct_stats
docker-compose -f docker/docker-compose.yml logs -f

# View status
docker-compose -f docker/docker-compose.yml ps
```

---

## Production Deployment

### 5. Publishing the Webapp

#### Prerequisites
- Docker and docker-compose installed on production server
- SSL certificates (optional but recommended)
- Domain name configured

#### Deployment Steps

1. **Copy project to server**:
   ```bash
   # On your local machine
   rsync -av --exclude='venv' --exclude='__pycache__' \
     /home/alan/Documents/code/fct_stats/ \
     user@server:/opt/fct_stats/
   ```

2. **Copy SSL certificates** (if using HTTPS):
   ```bash
   # On server
   mkdir -p /opt/fct_stats/docker/ssl
   # Copy your SSL cert and key files to this directory
   ```

3. **Start the application**:
   ```bash
   # On server
   cd /opt/fct_stats/docker
   docker-compose up -d
   ```

4. **Verify deployment**:
   ```bash
   docker-compose ps
   docker-compose logs -f webapp
   ```

#### Update Deployment

When you have new code changes:

```bash
# On local machine - push changes to server
rsync -av --exclude='venv' --exclude='__pycache__' \
  /home/alan/Documents/code/fct_stats/ \
  user@server:/opt/fct_stats/

# On server - rebuild and restart
cd /opt/fct_stats/docker
docker-compose down
docker-compose rm -f
docker-compose build
docker-compose up -d
```

#### Managing the Service

```bash
# Stop the service
docker-compose down

# View logs
docker-compose logs -f

# Restart specific service
docker-compose restart webapp

# View resource usage
docker stats
```

---

### 6. Publishing the Database

The database is updated separately from the webapp deployment.

#### Development → Production Database Sync

1. **After scraping new meets on your local machine**:
   ```bash
   # Verify database locally
   sqlite3 data/fct_stats.db "SELECT COUNT(*) FROM results;"
   ```

2. **Copy database to production server**:
   ```bash
   # Stop webapp temporarily to avoid locks
   ssh user@server "cd /opt/fct_stats/docker && docker-compose stop webapp"
   
   # Copy database
   scp data/fct_stats.db user@server:/opt/fct_stats/data/
   
   # Restart webapp
   ssh user@server "cd /opt/fct_stats/docker && docker-compose start webapp"
   ```

3. **Alternative: Direct scraping on server**:
   ```bash
   # On server
   cd /opt/fct_stats
   docker-compose -f docker/docker-compose.yml run --rm scraper \
     python -m scraper.scraper data/meets/2025/meet_config.yaml
   ```

#### Database Backups

Create regular backups:

```bash
# On server
mkdir -p /opt/fct_stats/backups
sqlite3 /opt/fct_stats/data/fct_stats.db ".backup '/opt/fct_stats/backups/fct_stats_$(date +%Y%m%d).db'"

# Automated backup (add to crontab)
0 2 * * * sqlite3 /opt/fct_stats/data/fct_stats.db ".backup '/opt/fct_stats/backups/fct_stats_$(date +\%Y\%m\%d).db'"
```

#### Database Maintenance

```bash
# Verify database integrity
sqlite3 data/fct_stats.db "PRAGMA integrity_check;"

# Optimize database
sqlite3 data/fct_stats.db "VACUUM;"

# View database stats
sqlite3 data/fct_stats.db << EOF
SELECT 'Athletes:', COUNT(*) FROM athletes;
SELECT 'Events:', COUNT(*) FROM events;
SELECT 'Meets:', COUNT(*) FROM meets;
SELECT 'Results:', COUNT(*) FROM results;
EOF
```

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
- Verify database exists: `ls -lh data/fct_stats.db`
- Check database has data: `sqlite3 data/fct_stats.db "SELECT COUNT(*) FROM results;"`
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
- If no backup, check integrity: `sqlite3 data/fct_stats.db "PRAGMA integrity_check;"`

---

## Project Structure

```
fct_stats/
├── config/              # Configuration files
│   ├── canonical_events.yaml
│   └── schools.yaml
├── data/
│   ├── fct_stats.db    # SQLite database
│   ├── meets/          # Meet configuration YAMLs
│   └── pages/          # Downloaded HTML results
├── database/
│   └── schema.sql      # Database schema
├── docker/             # Docker configuration
│   ├── docker-compose.yml
│   ├── Dockerfile.webapp
│   └── nginx.conf
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
