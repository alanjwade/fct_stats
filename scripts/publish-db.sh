#!/bin/bash
# Publish FCT Stats database to homelab

set -e

SOURCE_DB="/home/alan/Documents/code/fct_stats/data/fct_stats.db"
TARGET_DIR="$HOME/homelab/fct_stats/data"
TARGET_DB="$TARGET_DIR/fct_stats.db"
BACKUP_DIR="$HOME/homelab/fct_stats/backups"

echo "Publishing FCT Stats database to homelab..."
echo "Source: $SOURCE_DB"
echo "Target: $TARGET_DB"
echo ""

# Create target directory if it doesn't exist
mkdir -p "$TARGET_DIR"
mkdir -p "$BACKUP_DIR"

# Check if source database exists
if [ ! -f "$SOURCE_DB" ]; then
    echo "Error: Source database not found at $SOURCE_DB"
    exit 1
fi

# Backup existing database if it exists
if [ -f "$TARGET_DB" ]; then
    BACKUP_FILE="$BACKUP_DIR/fct_stats_$(date +%Y%m%d_%H%M%S).db"
    echo "Backing up existing database to $BACKUP_FILE"
    cp "$TARGET_DB" "$BACKUP_FILE"
fi

# Copy database
echo "Copying database..."
cp "$SOURCE_DB" "$TARGET_DB"

# Verify the copy
if [ -f "$TARGET_DB" ]; then
    echo ""
    echo "✓ Database published successfully"
    
    # Show stats
    echo ""
    echo "Database stats:"
    sqlite3 "$TARGET_DB" << EOF
SELECT 'Athletes: ' || COUNT(*) FROM athletes;
SELECT 'Events: ' || COUNT(*) FROM events;
SELECT 'Meets: ' || COUNT(*) FROM meets;
SELECT 'Results: ' || COUNT(*) FROM results;
EOF
else
    echo "Error: Database copy failed"
    exit 1
fi

echo ""
echo "Database ready at: $TARGET_DB"
