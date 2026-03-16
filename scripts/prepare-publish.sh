#!/bin/bash
# Prepare config files for publishing
# Syncs meets_{year}.json from data/sources/current/ into config/ so it
# gets picked up by the webapp and included in the publish rsync.

set -e

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPTS_DIR")"

YEAR=$(date +%Y)
SOURCE="$PROJECT_DIR/data/sources/current/$YEAR/meets_${YEAR}.json"
TARGET="$PROJECT_DIR/config/meets_${YEAR}.json"

echo "Preparing config for publishing (year: $YEAR)..."

if [ -f "$SOURCE" ]; then
    cp "$SOURCE" "$TARGET"
    MEET_COUNT=$(python3 -c "import json; d=json.load(open('$TARGET')); print(len(d.get('meets', [])))" 2>/dev/null || echo "?")
    echo "✓ Synced meets_${YEAR}.json to config/ ($MEET_COUNT meets)"
else
    echo "Warning: $SOURCE not found, skipping meets config sync"
fi
