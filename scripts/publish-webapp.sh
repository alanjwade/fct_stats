#!/bin/bash
# Publish FCT Stats webapp to homelab

set -e

SOURCE_DIR="/home/alan/Documents/code/fct_stats"
TARGET_DIR="$HOME/homelab/fct_stats"

echo "Publishing FCT Stats webapp to homelab..."
echo "Source: $SOURCE_DIR"
echo "Target: $TARGET_DIR"
echo ""

# Create target directory if it doesn't exist
mkdir -p "$TARGET_DIR"

# Sync project files, keeping only production-necessary directories
rsync -av --delete \
  --exclude='venv/' \
  --exclude='.venv/' \
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
  "$SOURCE_DIR/" "$TARGET_DIR/"

echo ""
echo "✓ Webapp files published to $TARGET_DIR"
echo ""
echo "Next steps:"
echo "  1. Publish database: ./scripts/publish-db.sh"
echo "  2. Start services: cd ~/homelab/fct_stats && docker-compose -f docker/docker-compose.yml up -d"
