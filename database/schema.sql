-- Fort Collins Track Stats Database Schema
-- SQLite

-- Athletes from Fort Collins High School
CREATE TABLE IF NOT EXISTS athletes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    gender TEXT CHECK(gender IN ('M', 'F')),
    graduation_year INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(first_name, last_name, graduation_year)
);

-- Canonical events
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    category TEXT,
    distance_meters REAL,
    timed BOOLEAN DEFAULT TRUE,
    lower_is_better BOOLEAN DEFAULT TRUE,
    is_relay BOOLEAN DEFAULT FALSE,
    gender_specific TEXT CHECK(gender_specific IN ('M', 'F') OR gender_specific IS NULL)
);

-- Meets/competitions
CREATE TABLE IF NOT EXISTS meets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    meet_date DATE,
    venue TEXT,
    location TEXT,
    season TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(name, meet_date)
);

-- Individual results
CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    athlete_id INTEGER NOT NULL REFERENCES athletes(id),
    event_id INTEGER NOT NULL REFERENCES events(id),
    meet_id INTEGER NOT NULL REFERENCES meets(id),
    mark REAL NOT NULL,
    mark_display TEXT,
    place INTEGER,
    level TEXT CHECK(level IN ('varsity', 'jv', 'open')),
    wind REAL,
    heat INTEGER,
    lane INTEGER,
    flight INTEGER,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(athlete_id, event_id, meet_id)
);

-- Relay team members (for relay events)
CREATE TABLE IF NOT EXISTS relay_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    result_id INTEGER NOT NULL REFERENCES results(id),
    athlete_id INTEGER NOT NULL REFERENCES athletes(id),
    leg_order INTEGER CHECK(leg_order BETWEEN 1 AND 4),
    split_time REAL,
    UNIQUE(result_id, athlete_id)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_results_athlete ON results(athlete_id);
CREATE INDEX IF NOT EXISTS idx_results_event ON results(event_id);
CREATE INDEX IF NOT EXISTS idx_results_meet ON results(meet_id);
CREATE INDEX IF NOT EXISTS idx_athletes_name ON athletes(last_name, first_name);
CREATE INDEX IF NOT EXISTS idx_athletes_gender ON athletes(gender);
CREATE INDEX IF NOT EXISTS idx_meets_season ON meets(season);
CREATE INDEX IF NOT EXISTS idx_meets_date ON meets(meet_date);

-- Views for common queries

-- Personal Records (PRs) for each athlete/event combination
CREATE VIEW IF NOT EXISTS athlete_prs AS
SELECT 
    a.id as athlete_id,
    a.first_name,
    a.last_name,
    a.gender,
    a.graduation_year,
    e.id as event_id,
    e.name as event_name,
    e.lower_is_better,
    CASE 
        WHEN e.lower_is_better THEN MIN(r.mark)
        ELSE MAX(r.mark)
    END as pr_mark,
    r.mark_display as pr_display,
    m.meet_date as pr_date,
    m.name as pr_meet
FROM athletes a
JOIN results r ON a.id = r.athlete_id
JOIN events e ON r.event_id = e.id
JOIN meets m ON r.meet_id = m.id
GROUP BY a.id, e.id
HAVING r.mark = CASE 
    WHEN e.lower_is_better THEN MIN(r.mark)
    ELSE MAX(r.mark)
END;

-- Team bests for each event (all-time)
CREATE VIEW IF NOT EXISTS team_bests_alltime AS
SELECT 
    e.id as event_id,
    e.name as event_name,
    e.category,
    a.gender,
    CASE 
        WHEN e.lower_is_better THEN MIN(r.mark)
        ELSE MAX(r.mark)
    END as best_mark,
    r.mark_display as best_display,
    a.first_name || ' ' || a.last_name as athlete_name,
    a.id as athlete_id,
    m.meet_date,
    m.name as meet_name,
    m.season
FROM results r
JOIN athletes a ON r.athlete_id = a.id
JOIN events e ON r.event_id = e.id
JOIN meets m ON r.meet_id = m.id
GROUP BY e.id, a.gender
HAVING r.mark = CASE 
    WHEN e.lower_is_better THEN MIN(r.mark)
    ELSE MAX(r.mark)
END;

-- Team bests for each event by season
CREATE VIEW IF NOT EXISTS team_bests_by_season AS
SELECT 
    e.id as event_id,
    e.name as event_name,
    e.category,
    a.gender,
    m.season,
    CASE 
        WHEN e.lower_is_better THEN MIN(r.mark)
        ELSE MAX(r.mark)
    END as best_mark,
    r.mark_display as best_display,
    a.first_name || ' ' || a.last_name as athlete_name,
    a.id as athlete_id,
    m.meet_date,
    m.name as meet_name
FROM results r
JOIN athletes a ON r.athlete_id = a.id
JOIN events e ON r.event_id = e.id
JOIN meets m ON r.meet_id = m.id
GROUP BY e.id, a.gender, m.season
HAVING r.mark = CASE 
    WHEN e.lower_is_better THEN MIN(r.mark)
    ELSE MAX(r.mark)
END;

-- Analytics page views (privacy-preserving)
CREATE TABLE IF NOT EXISTS page_views (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    page_type TEXT NOT NULL,  -- 'athlete', 'event', 'team_bests', 'events_list', 'home'
    page_detail TEXT,          -- event name or team name (NULL for athlete pages for privacy)
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Index for analytics queries
CREATE INDEX IF NOT EXISTS idx_page_views_timestamp ON page_views(timestamp);
CREATE INDEX IF NOT EXISTS idx_page_views_page_type ON page_views(page_type);
