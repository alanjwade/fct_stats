#!/bin/bash
# Restart FCT Stats services in homelab (rebuild if needed)

set -e

HOMELAB_DIR="$HOME/homelab/fct_stats"

if [ ! -d "$HOMELAB_DIR" ]; then
    echo "Error: Homelab directory not found at $HOMELAB_DIR"
    echo "Run ./scripts/publish-all.sh first"
    exit 1
fi

cd "$HOMELAB_DIR"

echo "Stopping services..."
docker-compose -f docker/docker-compose.yml down

echo ""
echo "Rebuilding and starting services..."
docker-compose -f docker/docker-compose.yml up -d --build

echo ""
echo "✓ Services restarted"
echo ""
echo "View logs:"
echo "  docker-compose -f docker/docker-compose.yml logs -f"
