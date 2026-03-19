#!/usr/bin/env python3
"""
Single entry point for all data management operations.

Usage:
    python manage_data.py rebuild-all
        Wipe the database and re-ingest everything from snapshots:
        historical records → 2025 meets → 2026 gsheet snapshot.
        Does NOT re-fetch from Google Sheets; uses the existing snapshot.

    python manage_data.py refresh-2026 --url "https://docs.google.com/..."
        Wipe 2026 data from DB, re-fetch the Google Sheet, save a fresh
        snapshot to data/snapshots/2026/gsheet_2026.json, then ingest it.

    python manage_data.py ingest-2026
        Wipe 2026 data from DB and re-ingest the existing
        data/snapshots/2026/gsheet_2026.json.  No network required.

    python manage_data.py reparse-frozen 2025 --force
        Re-parse the frozen 2025 source (ODS spreadsheet) and overwrite
        data/snapshots/2025/.  You must follow this with rebuild-all to
        get the new data into the database.

Options common to all commands:
    --db PATH     Override the database path (default: data/db/fct_stats.db)
    --debug       Enable verbose logging
"""

import argparse
import json
import logging
import subprocess
import sys
import time
from pathlib import Path

# Ensure project root is on sys.path for scraper imports
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from scraper.database import get_database

logger = logging.getLogger(__name__)

GSHEET_SNAPSHOT = ROOT / "data" / "snapshots" / "2026" / "gsheet_2026.json"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _wipe_season(db, season: str) -> None:
    """Delete all results and meets for a given season from the database."""
    logger.info(f"Wiping season {season!r} from database...")
    with db.get_connection() as conn:
        cursor = conn.cursor()
        # Delete relay_members for results in this season's meets
        cursor.execute(
            """
            DELETE FROM relay_members
            WHERE result_id IN (
                SELECT r.id FROM results r
                JOIN meets m ON r.meet_id = m.id
                WHERE m.season = ?
            )
            """,
            (season,),
        )
        relay_rows = cursor.rowcount
        # Delete results for this season's meets
        cursor.execute(
            "DELETE FROM results WHERE meet_id IN (SELECT id FROM meets WHERE season = ?)",
            (season,),
        )
        result_rows = cursor.rowcount
        # Delete meets for this season
        cursor.execute("DELETE FROM meets WHERE season = ?", (season,))
        meet_rows = cursor.rowcount
        conn.commit()
    logger.info(
        f"  Wiped season {season}: {meet_rows} meets, "
        f"{result_rows} results, {relay_rows} relay_member rows removed"
    )


def _ingest_historical(db_path: str | None) -> None:
    logger.info("─── Ingesting historical records ───")
    from scripts.import_historical_records import import_historical_records
    import_historical_records(db_path)


def _ingest_2025(db_path: str | None) -> None:
    logger.info("─── Ingesting 2025 meet snapshots ───")
    from scripts.import_from_parsed_meets import import_all_parsed_meets
    # clear_db=False because we manage the DB wipe at the command level
    import_all_parsed_meets(db_path, clear_db=False)


def _ingest_2026_from_snapshot(db_path: str | None, snapshot_path: Path) -> None:
    logger.info(f"─── Ingesting 2026 from {snapshot_path} ───")
    from scripts.import_from_gsheet import import_all
    if not snapshot_path.exists():
        logger.error(f"Snapshot not found: {snapshot_path}")
        logger.info("Run: python manage_data.py refresh-2026 --url <SHEET_URL>")
        sys.exit(1)
    with open(snapshot_path) as f:
        gsheet_data = json.load(f)
    import_all(gsheet_data, db_path=db_path)


def _fetch_and_save_gsheet(url: str, save_path: Path) -> list:
    """Fetch all sheets from Google Sheets, save JSON, return parsed data."""
    logger.info("Fetching Google Sheet...")
    sys.path.insert(0, str(ROOT / "scripts"))
    import explore_gsheet as eg

    sheet_id = eg.sheet_id_from_url(url)
    gsheet_data = []
    for i, sheet_name in enumerate(eg.SHEET_NAMES):
        if i > 0:
            time.sleep(2)
        logger.info(f"  Fetching sheet: {sheet_name}")
        rows = eg.fetch_sheet_as_csv(sheet_id, sheet_name, eg.DEFAULT_GIDS)
        parsed = eg.parse_sheet(rows, sheet_name)
        gsheet_data.append(parsed)

    save_path.parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "w") as f:
        json.dump(gsheet_data, f, indent=2)
    logger.info(f"Snapshot saved to {save_path}")
    return gsheet_data


def _db_counts(db) -> dict[str, int]:
    with db.get_connection() as conn:
        return {
            "athletes": conn.execute("SELECT COUNT(*) FROM athletes").fetchone()[0],
            "meets":    conn.execute("SELECT COUNT(*) FROM meets").fetchone()[0],
            "results":  conn.execute("SELECT COUNT(*) FROM results").fetchone()[0],
        }


def _print_summary(db) -> None:
    counts = _db_counts(db)
    logger.info("=" * 60)
    logger.info("DATABASE SUMMARY")
    logger.info(f"  Athletes: {counts['athletes']}")
    logger.info(f"  Meets:    {counts['meets']}")
    logger.info(f"  Results:  {counts['results']}")
    logger.info("=" * 60)


# ─────────────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────────────

def cmd_rebuild_all(args) -> None:
    """Wipe DB and re-ingest all data from snapshots."""
    db = get_database(args.db)
    logger.info("Clearing entire database...")
    db.clear_all()
    _ingest_historical(args.db)
    _ingest_2025(args.db)
    _ingest_2026_from_snapshot(args.db, GSHEET_SNAPSHOT)
    _print_summary(db)


def cmd_refresh_2026(args) -> None:
    """Wipe 2026 from DB, re-fetch sheet, save snapshot, ingest."""
    if not args.url:
        logger.error("--url is required for refresh-2026")
        sys.exit(1)
    db = get_database(args.db)
    _wipe_season(db, "2026")
    gsheet_data = _fetch_and_save_gsheet(args.url, GSHEET_SNAPSHOT)
    from scripts.import_from_gsheet import import_all
    import_all(gsheet_data, db_path=args.db)
    _print_summary(db)


def cmd_ingest_2026(args) -> None:
    """Wipe 2026 from DB and re-ingest from existing snapshot. No network."""
    db = get_database(args.db)
    _wipe_season(db, "2026")
    _ingest_2026_from_snapshot(args.db, GSHEET_SNAPSHOT)
    _print_summary(db)


def cmd_reparse_frozen(args) -> None:
    """Re-parse a frozen year's source data and overwrite its snapshot files."""
    year = args.year
    if not args.force:
        logger.error(
            f"Re-parsing frozen year {year} will overwrite existing snapshots.\n"
            f"Re-run with --force to proceed, then run:\n"
            f"  python manage_data.py rebuild-all"
        )
        sys.exit(1)

    if year == "2025":
        logger.info("Re-parsing 2025 ODS performance list...")
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "parse_performance_list.py")],
            check=False,
        )
        if result.returncode != 0:
            logger.error("parse_performance_list.py failed")
            sys.exit(result.returncode)
        logger.info(
            "2025 snapshots updated.\n"
            "Run the following to rebuild the database:\n"
            "  python manage_data.py rebuild-all"
        )
    else:
        logger.error(
            f"Re-parsing year {year!r} is not supported by this script.\n"
            f"Supported frozen years: 2025"
        )
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="FCT Stats data management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--db", help="Path to database file (default: auto-detected)")
    parser.add_argument("--debug", action="store_true", help="Verbose logging")

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    subparsers.required = True

    # rebuild-all
    subparsers.add_parser(
        "rebuild-all",
        help="Wipe DB and re-ingest all data from snapshots",
    )

    # refresh-2026
    p_refresh = subparsers.add_parser(
        "refresh-2026",
        help="Re-fetch Google Sheet, save snapshot, wipe 2026, ingest",
    )
    p_refresh.add_argument(
        "--url",
        required=True,
        metavar="SHEETS_URL",
        help="Public Google Sheets URL",
    )

    # ingest-2026
    subparsers.add_parser(
        "ingest-2026",
        help="Wipe 2026 from DB and re-ingest existing snapshot (no network)",
    )

    # reparse-frozen
    p_reparse = subparsers.add_parser(
        "reparse-frozen",
        help="Re-parse a frozen year's source data (--force required)",
    )
    p_reparse.add_argument("year", help="Year to re-parse (e.g. 2025)")
    p_reparse.add_argument(
        "--force",
        action="store_true",
        help="Required to confirm overwriting existing snapshots",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(message)s",
    )

    dispatch = {
        "rebuild-all":     cmd_rebuild_all,
        "refresh-2026":    cmd_refresh_2026,
        "ingest-2026":     cmd_ingest_2026,
        "reparse-frozen":  cmd_reparse_frozen,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
