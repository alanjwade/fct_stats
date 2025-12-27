#!/bin/bash
# Start FCT Stats services in homelab

set -e

HOMELAB_DIR="$HOME/homelab/fct_stats"

if [ ! -d "$HOMELAB_DIR" ]; then
    echo "Error: Homelab directory not found at $HOMELAB_DIR"
    echo "Run ./scripts/publish-all.sh first"
    exit 1
fi

cd "$HOMELAB_DIR"

echo "Starting FCT Stats services..."
docker-compose -f docker/docker-compose.yml up -d

echo ""
echo "✓ Services started"
echo ""
echo "View status:"
echo "  docker-compose -f docker/docker-compose.yml ps"
echo ""
echo "View logs:"
echo "  docker-compose -f docker/docker-compose.yml logs -f"
echo ""
echo "Access the site at:"
echo "  http://localhost:80"
