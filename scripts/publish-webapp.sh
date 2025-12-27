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

# Sync project files, excluding development artifacts
rsync -av --delete \
  --exclude='venv/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='.git/' \
  --exclude='data/fct_stats.db' \
  --exclude='data/pages/' \
  --exclude='data/meets/' \
  --exclude='.vscode/' \
  --exclude='*.log' \
  "$SOURCE_DIR/" "$TARGET_DIR/"

echo ""
echo "✓ Webapp files published to $TARGET_DIR"
echo ""
echo "Next steps:"
echo "  1. Publish database: ./scripts/publish-db.sh"
echo "  2. Start services: cd ~/homelab/fct_stats && docker-compose -f docker/docker-compose.yml up -d"
