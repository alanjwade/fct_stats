#!/bin/bash
# Prepare config files for publishing
# config/meets_{year}.json is the canonical location — no sync needed.
# (Previously synced from data/sources/current/ but that path no longer exists.)

set -e

YEAR=$(date +%Y)
echo "Preparing config for publishing (year: $YEAR)..."
echo "✓ config/meets_${YEAR}.json is canonical (no sync required)"
