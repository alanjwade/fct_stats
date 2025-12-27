#!/bin/bash
# Publish both webapp and database to homelab

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==================================================================="
echo "Publishing FCT Stats to homelab"
echo "==================================================================="
echo ""

# Publish webapp
bash "$SCRIPT_DIR/publish-webapp.sh"

echo ""
echo "==================================================================="
echo ""

# Publish database
bash "$SCRIPT_DIR/publish-db.sh"

echo ""
echo "==================================================================="
echo "Deployment complete!"
echo "==================================================================="
echo ""
echo "To start the services:"
echo "  cd ~/homelab/fct_stats"
echo "  docker-compose -f docker/docker-compose.yml up -d"
echo ""
echo "To view logs:"
echo "  docker-compose -f docker/docker-compose.yml logs -f"
echo ""
echo "To stop the services:"
echo "  docker-compose -f docker/docker-compose.yml down"
