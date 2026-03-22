---
agent: agent
description: Run this prompt after a meet has been entered into the Google Sheet to re-import results, update the database, and publish to production.
model: Claude Sonnet 4.5
---

# Update Results After a Meet

Use this prompt whenever a meet has been added to the Google Sheet and you want
to pull the latest data into the database and push it live.

## What This Workflow Does

1. Re-fetches **all sheets** from the FCT Google Spreadsheet
2. Saves the snapshot to `data/snapshots/2026/gsheet_2026.json`
3. Imports any new results into `data/db/fct_stats.db` (skips duplicates)
4. Publishes the database to the homelab production server
5. Restarts the webapp so the live site reflects the new results

The calendar's "upcoming events" section updates automatically — no manual
change needed. The webapp compares event dates to today's date at request time,
so once a meet date passes it disappears from the upcoming list on its own.

---

## Step 1: Re-fetch the Spreadsheet and Import

```bash
.venv/bin/python3 scripts/import_from_gsheet.py \
    --fetch \
    --url "https://docs.google.com/spreadsheets/d/1avGZOoj0we3cyuMSTWbBQGdJ-i7XGmZa" \
    --save data/snapshots/2026/gsheet_2026.json
```

Expected output:
- Each sheet (`2026 Girls Track`, `2026 Boys Track`, etc.) is fetched and logged
- Summary at the end shows `Added: N` (new results) and `Skipped: N` (already in DB)
- New results should be > 0 if the meet was entered in the sheet

If `Added: 0` on every sheet, the meet name in the sheet may not match any entry
in `MEET_INFO` in `scripts/import_from_gsheet.py`. See **Troubleshooting** below.

---

## Step 2: Publish the Database

```bash
./scripts/publish-db.sh
```

This backs up the existing production database and copies the updated one over.
Check the stats it prints — `Results` should be higher than before.

---

## Step 3: Restart the Production Server

```bash
./scripts/homelab-restart.sh
```

Wait for `✓ Services restarted`, then verify at **https://track.fchsrunning.org**.

---

## Troubleshooting: Meet Name Not Recognized

If `Added: 0` after a meet that was clearly entered, the meet name in the
spreadsheet column header doesn't match any key in `MEET_INFO`.

1. Check what name the coaches used in the sheet header:
   ```bash
   .venv/bin/python3 scripts/explore_gsheet.py \
       --url "https://docs.google.com/spreadsheets/d/1avGZOoj0we3cyuMSTWbBQGdJ-i7XGmZa" \
       --dump 2>&1 | grep -A2 "meet\|Meet\|MEET" | head -40
   ```

2. Look for a `WARNING: Unknown meet name:` line in the import output by re-running
   with `--debug`:
   ```bash
   .venv/bin/python3 scripts/import_from_gsheet.py \
       --input data/snapshots/2026/gsheet_2026.json \
       --debug 2>&1 | grep -i "unknown\|warning"
   ```

3. Add the new name to `MEET_INFO` in `scripts/import_from_gsheet.py`:
   ```python
   "Exact Sheet Name": {
       "canonical": "Canonical Meet Name",   # omit if same
       "date": "2026-MM-DD",
       "level": "varsity",                   # or "jv"
   },
   ```

4. Re-run Step 1 (import only, no need to re-fetch):
   ```bash
   .venv/bin/python3 scripts/import_from_gsheet.py \
       --input data/snapshots/2026/gsheet_2026.json
   ```

---

## Troubleshooting: GID Warnings

You may see warnings like:
```
WARNING: Could not determine GID for '2026 Girls Field'. Falling back to gviz...
```

These are safe to ignore — the script falls back to Google's gviz endpoint and
fetches the data anyway. The GID lookup is only needed when two sheets happen to
have the same dimensions (which is rarely a problem in practice).

---

## Full Command Reference

| Task | Command |
|------|---------|
| Fetch sheet + import | `.venv/bin/python3 scripts/import_from_gsheet.py --fetch --url "..." --save data/snapshots/2026/gsheet_2026.json` |
| Import from saved snapshot | `.venv/bin/python3 scripts/import_from_gsheet.py --input data/snapshots/2026/gsheet_2026.json` |
| Dry run (no DB writes) | add `--dry-run` to either import command |
| Publish DB only | `./scripts/publish-db.sh` |
| Publish webapp + DB | `./scripts/publish-all.sh` |
| Restart production | `./scripts/homelab-restart.sh` |
| Check production logs | `cd ~/homelab/fct_stats && docker-compose -f docker/docker-compose.yml logs -f webapp` |
