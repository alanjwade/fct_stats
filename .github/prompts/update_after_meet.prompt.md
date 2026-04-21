---
agent: agent
description: Run this prompt after a meet has been entered into the Google Sheet to re-import results, update the database, and publish to production.
---

# Update Results After a Meet

Use this prompt whenever a meet has been added to the Google Sheet and you want
to pull the latest data into the database and push it live.

## What This Workflow Does

1. Re-fetches **all sheets** from the FCT Google Spreadsheet
2. Saves the snapshot to `data/snapshots/2026/gsheet_2026.json`
3. Imports any new results into `data/db/fct_stats.db` (skips duplicates)

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
- Summary at the end shows:
  - `Added: N` (new results written to DB)
  - `Skipped: N` (duplicates already in DB)
  - `No mark: N` (blank cells, DNS/DNF/DQ entries)
  - `Errors: N` (event matching failures)

**What to look for:**
- `Added` should be > 0 if the meet was entered in the sheet
- If `Added: 0`, check for meet name mismatches (see **Data Quality Checks** below)
- If you see `WARNING: Unknown meet name:` in the output, that meet has no date
- `Errors` should typically be 0 (check if > 0)

---

## Data Quality Checks

After importing, verify data quality to catch issues like missing dates, 
unrecognized meet names, or suspicious results.

### Check for Meets with Null Dates

Meets with null dates won't sort correctly and may not appear in season-specific views:

```bash
sqlite3 data/db/fct_stats.db \
  "SELECT DISTINCT m.id, m.name, m.season, m.meet_date, COUNT(r.id) as num_results
   FROM meets m
   LEFT JOIN results r ON m.id = r.meet_id
   WHERE m.meet_date IS NULL AND m.season = '2026'
   GROUP BY m.id
   ORDER BY m.name;"
```

**Fix:** If a meet appears with a null date, add it to `MEET_INFO` in 
[scripts/import_from_gsheet.py](scripts/import_from_gsheet.py) with the correct date.

### Check for Unknown Meet Names

Look for `WARNING: Unknown meet name:` messages in the import log:

```bash
.venv/bin/python3 scripts/import_from_gsheet.py \
    --input data/snapshots/2026/gsheet_2026.json \
    --debug 2>&1 | grep -i "unknown\|warning"
```

Or check what meet names exist in the snapshot:

```bash
.venv/bin/python3 scripts/explore_gsheet.py \
    --url "https://docs.google.com/spreadsheets/d/1avGZOoj0we3cyuMSTWbBQGdJ-i7XGmZa" \
    --dump 2>&1 | grep -A2 "meet\|Meet\|MEET" | head -40
```

**Fix:** Add unrecognized meet names to `MEET_INFO` in 
[scripts/import_from_gsheet.py](scripts/import_from_gsheet.py):

```python
"Exact Sheet Name": {
    "canonical": "Canonical Meet Name",   # omit if same
    "date": "2026-MM-DD",
    "level": "varsity",                   # or "jv"
},
```

Then re-import:

```bash
.venv/bin/python3 scripts/import_from_gsheet.py \
    --input data/snapshots/2026/gsheet_2026.json
```

### Check for Outlier Results

Look for suspiciously fast/far performances that might be data entry errors:

```bash
# Extremely fast short sprints (< 10 seconds for 100m)
sqlite3 data/db/fct_stats.db \
  "SELECT a.first_name || ' ' || a.last_name as athlete, 
          e.name as event, m.name as meet, 
          r.mark_display, r.mark
   FROM results r
   JOIN athletes a ON r.athlete_id = a.id
   JOIN events e ON r.event_id = e.id
   JOIN meets m ON r.meet_id = m.id
   WHERE e.name LIKE '%100m%' 
     AND e.name NOT LIKE '%4x100m%'
     AND r.mark < 10.0
     AND m.season = '2026'
   ORDER BY r.mark;"

# Extremely long throws (> 70m / 230' for shot put)
sqlite3 data/db/fct_stats.db \
  "SELECT a.first_name || ' ' || a.last_name as athlete,
          e.name as event, m.name as meet,
          r.mark_display, r.mark
   FROM results r
   JOIN athletes a ON r.athlete_id = a.id
   JOIN events e ON r.event_id = e.id
   JOIN meets m ON r.meet_id = m.id
   WHERE e.name LIKE '%Shot Put%'
     AND r.mark > 70.0
     AND m.season = '2026'
   ORDER BY r.mark DESC;"

# Times that parsed as distance (check conversion errors)
sqlite3 data/db/fct_stats.db \
  "SELECT a.first_name || ' ' || a.last_name as athlete,
          e.name as event, m.name as meet,
          r.mark_display, r.mark
   FROM results r
   JOIN athletes a ON r.athlete_id = a.id
   JOIN events e ON r.event_id = e.id
   JOIN meets m ON r.meet_id = m.id
   WHERE e.timed = 1
     AND r.mark > 1000
     AND m.season = '2026'
   ORDER BY r.mark DESC LIMIT 20;"
```

**Fix:** Correct errors in the Google Sheet and re-run Step 1.

### Check Import Summary Stats

The import output shows summary counts. Look for anomalies:

```
Added:   0      ← If this is 0 but you added data, meet name doesn't match
Skipped: 145    ← High number means data was already imported
No mark: 23     ← Blank cells or unparseable marks (normal for DNS/DNF)
Errors:  0      ← Event matching failures or other issues
```

---

## Troubleshooting: Meet Name Not Recognized

If `Added: 0` after a meet that was clearly entered, the meet name in the
spreadsheet column header doesn't match any key in `MEET_INFO`.

Follow the steps in "Check for Unknown Meet Names" above.

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

## Publishing to Production (Optional)

When ready to push changes live, run:

```bash
./scripts/publish-homelab00.sh
```

This syncs all files and the database to homelab00 and restarts the Docker service.

Then verify at **https://track.fchsrunning.org**.

---

## Full Command Reference

| Task | Command |
|------|---------|
| Fetch sheet + import | `.venv/bin/python3 scripts/import_from_gsheet.py --fetch --url "https://docs.google.com/spreadsheets/d/1avGZOoj0we3cyuMSTWbBQGdJ-i7XGmZa" --save data/snapshots/2026/gsheet_2026.json` |
| Import from saved snapshot | `.venv/bin/python3 scripts/import_from_gsheet.py --input data/snapshots/2026/gsheet_2026.json` |
| Dry run (no DB writes) | add `--dry-run` to either import command |
| Publish + restart | `./scripts/publish-homelab00.sh` |
