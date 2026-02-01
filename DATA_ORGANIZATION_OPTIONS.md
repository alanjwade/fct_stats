# Data Directory Organization: Options Analysis

## Current State

```
data/
├── 2025/                           # SOURCE: 2025 config + ODS
│   ├── 2025 Track & Field Performance List.xlsx.ods
│   └── meets_2025.json
├── fct_stats.db                    # GENERATED: Database
├── historic/                       # SOURCE: Historical records markdown
│   ├── FCHS Boys Track & Field Records.docx.md
│   └── FCHS Girls Track & Field Records.docx.md
├── historical_records.json         # GENERATED: Parsed historical
├── meets/                          # SOURCE: Meet YAML configs
│   ├── 2024/
│   └── 2025/*.yaml
├── pages/                          # SOURCE: Meet result pages
│   ├── 2024/
│   └── 2025/*.html, *.txt
├── parsed_meets/                   # GENERATED: Parsed meet results
│   ├── 2025/*.json
│   └── historical_records.json
└── parsed_performance_list.json    # GENERATED: Parsed ODS
```

## Problem Areas
- **Mixing sources and generated**: Pages, YAML, and JSON are all mixed in top-level dirs
- **Ambiguous intent**: Hard to tell at a glance what's source vs what was generated
- **Flat top-level**: 8 top-level items, unclear hierarchy
- **Database location**: `fct_stats.db` at root level—is this source or generated?

---

## Option 1: Source/Generated Split (Clean & Explicit)

```
data/
├── sources/                        # ALL INPUT DATA (read-only in production)
│   ├── current/                    # Current season inputs
│   │   ├── 2025/
│   │   │   ├── meets_2025.json     # Meet metadata
│   │   │   └── 2025 Track & Field Performance List.xlsx.ods
│   │   ├── pages/
│   │   │   └── 2025/*.html, *.txt  # Meet result pages
│   │   └── meets/
│   │       └── 2025/*.yaml         # Meet YAML configs
│   └── historic/                   # Pre-2026 historical data
│       ├── records/
│       │   ├── FCHS Boys Track & Field Records.docx.md
│       │   └── FCHS Girls Track & Field Records.docx.md
│       └── meets/
│           └── 2024/               # (for comparison/archival)
│
├── generated/                      # ALL OUTPUT DATA (disposable, can regenerate)
│   ├── parsed/
│   │   ├── historical_records.json
│   │   ├── parsed_performance_list.json
│   │   └── parsed_meets/
│   │       ├── 2025/*.json
│   │       └── historical_records.json
│   └── db/
│       └── fct_stats.db
│
└── .gitignore                      # Ignore all of /generated (but keep /sources)
```

**Pros:**
- Crystal clear separation
- One directory to add to `.gitignore` (generated/)
- Easy to see what's source material
- Works well with version control (keep sources, ignore generated)

**Cons:**
- More nested directories
- Requires path updates in many scripts

---

## Option 2: By Data Type (Semantic Organization)

```
data/
├── raw/                            # SOURCE: Unprocessed input
│   ├── historical/
│   │   └── *.md
│   ├── spreadsheets/
│   │   └── *.ods, *.xlsx
│   └── pages/
│       └── 2025/
│           └── *.html, *.txt
│
├── config/                         # SOURCE: Configuration & metadata
│   ├── 2025/
│   │   └── meets_2025.json
│   └── meets/
│       └── 2025/*.yaml
│
├── parsed/                         # GENERATED: Normalized JSON
│   ├── meets/
│   │   └── 2025/*.json
│   └── records/
│       ├── historical_records.json
│       └── performance_list.json
│
└── db/
    └── fct_stats.db
```

**Pros:**
- Logical semantic grouping
- `raw/` is clearly source material
- Easy to reason about data flow
- Moderate path changes needed

**Cons:**
- Still mixing concepts (raw + config are both sources but split)
- `db/` is oddly alone
- May be over-structured

---

## Option 3: Year-Centric with Inputs/Outputs

```
data/
├── 2025/                          # All 2025-specific data
│   ├── input/
│   │   ├── config/
│   │   │   ├── meets_2025.json
│   │   │   └── *.yaml
│   │   ├── pages/
│   │   │   └── *.html, *.txt
│   │   └── spreadsheet/
│   │       └── 2025 Track & Field Performance List.xlsx.ods
│   ├── output/
│   │   ├── parsed_meets/*.json
│   │   ├── parsed_performance_list.json
│   │   └── cache/                # Optional: temp parsing files
│   │       └── *.tmp
│   └── db/
│       └── fct_stats.db
│
└── historic/                      # Pre-2026 data (separate year concept)
    ├── input/
    │   └── records/
    │       └── *.md
    └── output/
        └── historical_records.json
```

**Pros:**
- Year-centric (natural for track sports that think seasonally)
- Clear input/output at leaf level
- Works if you have multiple seasons
- Easy to archive/delete old years

**Cons:**
- Mixes database at 2025 level (database is multi-year)
- More nesting depth
- Trickier for historical data

---

## Option 4: Simple & Flat (Minimal Changes)

```
data/
├── sources/                       # Consolidate all inputs here
│   ├── 2025/
│   │   ├── 2025 Track & Field Performance List.xlsx.ods
│   │   └── meets_2025.json
│   ├── historic/
│   │   ├── FCHS Boys Track & Field Records.docx.md
│   │   └── FCHS Girls Track & Field Records.docx.md
│   ├── pages/                     # Move here
│   │   └── 2025/
│   └── meets/                     # Move here
│       └── 2025/*.yaml
│
├── fct_stats.db                   # Keep as-is
├── historical_records.json
├── parsed_performance_list.json
├── parsed_meets/
│   ├── 2025/*.json
│   └── historical_records.json
```

**Pros:**
- Minimal code changes
- Only rename directory
- Still improves clarity
- One `.gitignore` rule

**Cons:**
- Still has generated files at root
- Less semantic clarity
- Partial separation

---

## Recommendation

**I'd suggest Option 1** (Source/Generated Split):

```
data/
├── sources/
│   ├── current/2025/
│   │   ├── meets_2025.json
│   │   ├── 2025 Track & Field Performance List.xlsx.ods
│   │   └── (pages/ and meets/ as subdirs)
│   └── historic/
│       └── (historical markdown files)
│
├── generated/
│   ├── parsed/
│   │   ├── historical_records.json
│   │   ├── parsed_performance_list.json
│   │   └── meets/2025/*.json
│   └── db/
│       └── fct_stats.db
```

**Why:**
1. **Version control friendly**: Single `.gitignore` line for `/generated`
2. **Intent is clear**: Anyone can see what's input vs output at a glance
3. **Production ready**: Easy to set up CI/CD that preserves sources, regenerates outputs
4. **Scalable**: Adding future years/seasons fits naturally
5. **Maintenance**: Can safely delete `generated/` and rebuild anytime

**Migration cost:** ~10 path updates in scripts (moderate, one-time cost)

---

## Alternative: Hybrid (Option 1 + Option 4)

If you want minimal disruption but still clear separation:

```
data/
├── sources/               # Just move raw inputs here
│   ├── 2025/
│   ├── historic/
│   ├── pages/           # Move from data/pages
│   └── meets/           # Move from data/meets
│
├── fct_stats.db
├── historical_records.json
├── parsed_performance_list.json
└── parsed_meets/
```

This is **Option 4** essentially—simpler than Option 1, still groups sources clearly.

---

## What do you prefer?

Pick your favorite approach and I'll reorganize everything + update all script paths.
