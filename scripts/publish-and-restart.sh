#!/bin/bash
# Publish FCT Stats webapp and database to homelab00, then restart services

set -e

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

REMOTE_USER="homelab"
REMOTE_HOST="homelab00"
REMOTE_DIR="/home/homelab/homelab00-config/websites/volumes/sites/fct_web"

echo "=========================================="
echo "FCT Stats: Publish & Restart (homelab00)"
echo "=========================================="
echo ""

# Step 0: Prepare config files (sync meets data into config/)
echo "Step 0: Preparing config files..."
echo ""
bash "$SCRIPTS_DIR/prepare-publish.sh"

echo ""
echo "=========================================="
echo ""

# Step 1: Publish to homelab00
echo "Step 1: Publishing to homelab00..."
echo ""
bash "$SCRIPTS_DIR/publish-homelab00.sh"

echo ""
echo "=========================================="
echo ""

# Step 2: Restart Docker on homelab00 (rebuild fct_web in the websites compose project)
echo "Step 2: Restarting Docker services on homelab00..."
echo ""
ssh "$REMOTE_USER@$REMOTE_HOST" \
  "cd /home/homelab/homelab00-config/websites && docker compose up -d --build --force-recreate fct_web"

echo ""
echo "=========================================="
echo "✓ All done! Published to homelab00 and"
echo "  services restarted."
echo "=========================================="
