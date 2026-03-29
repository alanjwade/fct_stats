#!/bin/bash
# Deploy FCT Stats to homelab00 for testing
# Runs in production mode (gunicorn), accessible on port 8080

set -e

SOURCE_DIR="/home/alan/Documents/code/fct_stats"
REMOTE_USER="homelab"
REMOTE_HOST="homelab00"
REMOTE_DIR="/home/homelab/web/fchs_track"
SOURCE_DB="$SOURCE_DIR/data/db/fct_stats.db"

echo "==================================================================="
echo "Deploying FCT Stats to homelab00 (test server)"
echo "Target: $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR"
echo "==================================================================="
echo ""

# Step 1: Ensure remote directory exists
echo "Preparing remote directory..."
ssh "$REMOTE_USER@$REMOTE_HOST" "mkdir -p $REMOTE_DIR/data/db"

# Step 2: Sync project files (same exclusions as publish-webapp.sh)
echo "Syncing project files..."
rsync -av --delete \
  --exclude='.venv/' \
  --exclude='venv/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='.git/' \
  --exclude='.github/' \
  --exclude='.vscode/' \
  --exclude='.gitignore' \
  --exclude='*.log' \
  --exclude='*.md' \
  --exclude='scraper/' \
  --exclude='database/' \
  --exclude='scripts/' \
  --exclude='docs/' \
  --exclude='tmp/' \
  --exclude='nginx/' \
  --exclude='docker/certbot/' \
  --exclude='data/' \
  --exclude='check_cells.py' \
  --exclude='debug_*.py' \
  --exclude='find_*.py' \
  --exclude='quick_debug.py' \
  --exclude='show_*.py' \
  --exclude='test_*.py' \
  "$SOURCE_DIR/" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/"

echo ""
echo "✓ Project files synced"
echo ""

# Step 3: Sync database
echo "Syncing database..."
if [ ! -f "$SOURCE_DB" ]; then
    echo "Error: Source database not found at $SOURCE_DB"
    exit 1
fi

rsync -av "$SOURCE_DB" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/data/db/fct_stats.db"

echo ""
echo "✓ Database synced"
echo ""

# Step 4: Rebuild and restart Docker on homelab00
echo "Rebuilding and restarting Docker on homelab00..."
ssh "$REMOTE_USER@$REMOTE_HOST" bash << EOF
  set -e
  cd $REMOTE_DIR
  docker-compose -f docker/docker-compose.homelab00.yml down --remove-orphans
  docker-compose -f docker/docker-compose.homelab00.yml up -d --build
EOF

echo ""
echo "==================================================================="
echo "Deployment to homelab00 complete!"
echo "==================================================================="
echo ""
echo "Access the site at:"
echo "  http://homelab00:8081"
echo ""
echo "View logs:"
echo "  ssh $REMOTE_USER@$REMOTE_HOST 'cd $REMOTE_DIR && docker-compose -f docker/docker-compose.homelab00.yml logs -f'"
echo ""
echo "Stop the service:"
echo "  ssh $REMOTE_USER@$REMOTE_HOST 'cd $REMOTE_DIR && docker-compose -f docker/docker-compose.homelab00.yml down'"
