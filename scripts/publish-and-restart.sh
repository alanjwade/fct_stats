#!/bin/bash
# Publish FCT Stats webapp and database to homelab, then restart services

set -e

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPTS_DIR")"

echo "=========================================="
echo "FCT Stats: Publish & Restart"
echo "=========================================="
echo ""

# Step 0: Prepare config files (sync meets data into config/)
echo "Step 0: Preparing config files..."
echo ""
bash "$SCRIPTS_DIR/prepare-publish.sh"

echo ""
echo "=========================================="
echo ""

# Step 1: Publish webapp
echo "Step 1: Publishing webapp..."
echo ""
bash "$SCRIPTS_DIR/publish-webapp.sh"

echo ""
echo "=========================================="
echo ""

# Step 2: Publish database
echo "Step 2: Publishing database..."
echo ""
bash "$SCRIPTS_DIR/publish-db.sh"

echo ""
echo "=========================================="
echo ""

# Step 3: Restart services
echo "Step 3: Restarting Docker services..."
echo ""
bash "$SCRIPTS_DIR/homelab-restart.sh"

echo ""
echo "=========================================="
echo "✓ All done! Webapp and database published,"
echo "  and services restarted."
echo "=========================================="
