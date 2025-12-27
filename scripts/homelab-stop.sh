#!/bin/bash
# Stop FCT Stats services in homelab

set -e

HOMELAB_DIR="$HOME/homelab/fct_stats"

if [ ! -d "$HOMELAB_DIR" ]; then
    echo "Error: Homelab directory not found at $HOMELAB_DIR"
    exit 1
fi

cd "$HOMELAB_DIR"

echo "Stopping FCT Stats services..."
docker-compose -f docker/docker-compose.yml down

echo ""
echo "✓ Services stopped"
