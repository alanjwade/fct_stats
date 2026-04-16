#!/bin/bash
# Publish FCT Stats webapp and database to homelab00
# Target: homelab@homelab00:/home/homelab/homelab00-config/websites/volumes/sites/fct_web

set -e

SOURCE_DIR="/home/alan/Documents/code/fct_stats"
SOURCE_DB="$SOURCE_DIR/data/db/fct_stats.db"
REMOTE_USER="homelab"
REMOTE_HOST="homelab00"
REMOTE_DIR="/home/homelab/homelab00-config/websites/volumes/sites/fct_web"

echo "==================================================================="
echo "FCT Stats: Publish to homelab00"
echo "Target: $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR"
echo "==================================================================="
echo ""

# Step 1: Ensure remote directories exist
echo "Step 1: Preparing remote directories..."
ssh "$REMOTE_USER@$REMOTE_HOST" "mkdir -p $REMOTE_DIR/data/db $REMOTE_DIR/data/analytics"
echo "✓ Remote directories ready"
echo ""

# Step 2: Sync webapp and supporting files
echo "Step 2: Syncing webapp files..."
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
  --exclude='data/' \
  --exclude='docker/docker-compose.yml' \
  --exclude='docker/docker-compose.dev.yml' \
  --exclude='docker/Dockerfile.scraper' \
  --exclude='docker/nginx.conf' \
  --exclude='check_cells.py' \
  --exclude='debug_*.py' \
  --exclude='find_*.py' \
  --exclude='quick_debug.py' \
  --exclude='show_*.py' \
  --exclude='test_*.py' \
  "$SOURCE_DIR/" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/"
echo ""
echo "✓ Webapp files synced"
echo ""

# Step 3: Sync database
echo "Step 3: Syncing database..."
if [ ! -f "$SOURCE_DB" ]; then
    echo "Error: Source database not found at $SOURCE_DB"
    exit 1
fi
rsync -av "$SOURCE_DB" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/data/db/fct_stats.db"
echo ""
echo "✓ Database synced"
echo ""

echo "==================================================================="
echo "✓ Publish complete!"
echo ""
echo "Files are at: $REMOTE_DIR"
echo ""
echo "If this is the first deploy, start services on homelab00 with:"
echo "  ssh $REMOTE_USER@$REMOTE_HOST"
echo "  cd $REMOTE_DIR"
echo "  docker-compose -f docker/docker-compose.homelab00.yml up -d --build"
echo ""
echo "To restart after an update:"
echo "  ssh $REMOTE_USER@$REMOTE_HOST \\"
echo "    \"cd $REMOTE_DIR && docker-compose -f docker/docker-compose.homelab00.yml up -d --build --force-recreate\""
echo "==================================================================="
