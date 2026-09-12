#!/usr/bin/env bash
#
# bump_release.sh — create the next release tag for this app (target-agnostic).
#
# This script is the ONLY thing you run to ship a release. It knows nothing
# about where the app is deployed: it does NOT touch any compose file, host,
# or version file. The deployed tag is owned by homelab-infra (scripts/update-apps.sh).
#
# What it does on an otherwise clean git tree:
#   1. sanity-checks that the working tree is clean
#   2. reads the newest existing `vX.Y.Z` tag as the base version
#   3. computes the next version (patch by default; minor/major accepted)
#   4. pushes the current branch to origin (so the tag points at a pushed commit)
#   5. creates + pushes the new annotated `vX.Y.Z` tag
#
# Pushing the tag is what triggers CI to build & publish the Docker image; the
# image is built with APP_VERSION=<this tag>, which the webapp shows in its
# footer. No tracked file changes here — the release stays a clean operation.
#
# Usage:
#   ./bump_release.sh          # v0.0.1 -> v0.0.2
#   ./bump_release.sh minor     # v0.0.1 -> v0.1.0
#   ./bump_release.sh major     # v0.0.1 -> v1.0.0
#
# Requirements: run from inside this git repo; git on PATH.

set -euo pipefail

RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[1;33m'; BLUE=$'\033[0;34m'; NC=$'\033[0m'

BUMP_TYPE="${1:-patch}"
case "$BUMP_TYPE" in
    patch|minor|major) ;;
    *)
        echo -e "${RED}Error: invalid bump type '$BUMP_TYPE'. Must be 'major', 'minor', or 'patch'.${NC}" >&2
        exit 1
        ;;
esac

echo -e "${GREEN}Release version bump (${BUMP_TYPE})${NC}"
echo "====================================="

git rev-parse --git-dir >/dev/null 2>&1 || { echo -e "${RED}Error: not in a git repository.${NC}" >&2; exit 1; }

# Working tree must be clean for a clean release.
echo -e "${YELLOW}Checking for uncommitted changes...${NC}"
if ! git diff-index --quiet HEAD --; then
    echo -e "${RED}Error: uncommitted changes detected.${NC}" >&2
    git status --short
    exit 1
fi
if ! git diff-index --quiet --cached HEAD --; then
    echo -e "${RED}Error: staged changes detected.${NC}" >&2
    git status --short
    exit 1
fi
echo -e "${GREEN}OK working tree clean${NC}"
echo ""

# Base version = newest existing semver tag (vX.Y.Z). Fall back to 0.0.0.
BASE="$(git tag --sort=-v:refname | sed -n 's/^v\([0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*\)$/\1/p' | head -n1)"
BASE="${BASE:-0.0.0}"
[ -n "$BASE" ] || BASE="0.0.0"

IFS='.' read -r MAJOR MINOR PATCH <<< "$BASE"
case "$BUMP_TYPE" in
    major) MAJOR=$((MAJOR + 1)); MINOR=0; PATCH=0 ;;
    minor) MINOR=$((MINOR + 1)); PATCH=0 ;;
    patch) PATCH=$((PATCH + 1)) ;;
esac
NEW="v${MAJOR}.${MINOR}.${PATCH}"

echo "Current version: ${BLUE}${BASE}${NC}"
echo "New version    : ${BLUE}${NEW}${NC}"
echo ""

# If the branch is ahead of origin (e.g. the CI/workflow change isn't pushed
# yet), make sure our tag points at a commit that's actually on the remote so
# CI checks it out. `git push origin HEAD` is a no-op when already up to date.
echo -e "${YELLOW}Publishing current branch HEAD...${NC}"
if git push origin HEAD; then
    echo -e "${GREEN}OK HEAD is on the remote${NC}"
else
    echo -e "${RED}Error: could not push HEAD.${NC}" >&2
    exit 1
fi
echo ""

echo -e "${YELLOW}Creating tag ${NEW}...${NC}"
if git tag -a "$NEW" -m "Release version ${NEW}"; then
    echo -e "${GREEN}OK Tag ${BLUE}${NEW}${GREEN} created locally${NC}"
else
    echo -e "${RED}Error: failed to create tag.${NC}" >&2
    exit 1
fi

echo -e "${YELLOW}Pushing tag ${NEW} (triggers Docker build)...${NC}"
if git push origin "$NEW"; then
    echo -e "${GREEN}OK Tag ${BLUE}${NEW}${GREEN} pushed${NC}"
else
    echo -e "${RED}Error: failed to push tag. Push manually:${NC}" >&2
    echo "  git push origin ${NEW}"
    exit 1
fi

echo ""
echo -e "${GREEN}Release ${NEW} shipped.${NC}"
echo "CI will build  ghcr.io/alanjwade/fct-stats:${NEW}"
echo "Then, from the homelab-infra checkout: ./scripts/update-apps.sh fct-stats"
