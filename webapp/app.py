"""
Fort Collins Track Stats Web Application
"""

import calendar as cal_module
import json
import hashlib
import sys
import sqlite3
import logging
import os
import re
import yaml
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from contextlib import contextmanager
from flask import Flask, render_template, request, jsonify, g


def _load_excluded_from_records():
    config_path = Path(os.environ.get('CONFIG_PATH', Path(__file__).parent.parent / 'config')) / 'meet_names.yaml'
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    return set(cfg.get('excluded_from_records', []))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration
DATABASE_PATH = os.environ.get('DATABASE_PATH', str(Path(__file__).parent.parent / 'data' / 'db' / 'fct_stats.db'))

# Secret key for hidden analytics page (change this in production!)
ANALYTICS_SECRET = os.environ.get('ANALYTICS_SECRET', 'lambkin-purple-stats-2025')

# Separate analytics DB that persists across publish/deploy cycles
ANALYTICS_DB_PATH = os.environ.get('ANALYTICS_DB_PATH', str(Path(__file__).parent.parent / 'data' / 'analytics' / 'analytics.db'))
VISITOR_SALT = os.environ.get('VISITOR_SALT', 'fct-stats-visitor-2026')

# Common bot user agent patterns
BOT_PATTERNS = [
    r'bot', r'crawler', r'spider', r'scraper', r'headless',
    r'googlebot', r'bingbot', r'slurp', r'duckduckbot', r'baiduspider',
    r'yandexbot', r'sogou', r'exabot', r'facebot', r'ia_archiver',
    r'semrush', r'ahref', r'mj12bot', r'dotbot', r'petalbot',
    r'curl', r'wget', r'python-requests', r'python-urllib', r'httpx',
    r'axios', r'node-fetch', r'go-http-client', r'java/', r'libwww',
    r'apache-httpclient', r'okhttp', r'feedfetcher', r'mediapartners',
    r'adsbot', r'apis-google', r'lighthouse', r'chrome-lighthouse',
    r'pingdom', r'uptimerobot', r'statuscake', r'site24x7',
    r'phantomjs', r'selenium', r'puppeteer', r'playwright',
    r'facebookexternalhit', r'twitterbot', r'linkedinbot', r'slackbot',
    r'telegrambot', r'whatsapp', r'discordbot',
]
BOT_REGEX = re.compile('|'.join(BOT_PATTERNS), re.IGNORECASE)

# Top-level navigation pages to track (skip individual athlete/event pages)
TOP_LEVEL_PAGES = {
    'home', 'calendar', 'stats', 'athletes_list', 'athletes_list_2026',
    'events_list', 'team_bests', 'season_bests_2026', 'season_bests_2025',
}


def is_bot(user_agent):
    """Check if the user agent appears to be a bot."""
    if not user_agent:
        return True  # No user agent is suspicious
    return bool(BOT_REGEX.search(user_agent))


def get_visitor_hash(ip_address):
    """Generate a privacy-preserving daily hash for a visitor IP (not reversible)."""
    today = datetime.now(MOUNTAIN_TZ).strftime('%Y-%m-%d')
    raw = f"{VISITOR_SALT}:{today}:{ip_address or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def record_page_view(page_type, page_detail=None):
    """Record a page view for top-level pages only (bots filtered)."""
    if page_type not in TOP_LEVEL_PAGES:
        return  # Only track top-level navigation pages

    user_agent = request.headers.get('User-Agent', '')
    if is_bot(user_agent):
        return  # Don't track bots

    try:
        ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        if ip and ',' in ip:
            ip = ip.split(',')[0].strip()
        visitor_hash = get_visitor_hash(ip)

        with get_analytics_db_connection() as conn:
            conn.execute("""
                INSERT INTO page_views (page_type, visitor_hash)
                VALUES (?, ?)
            """, (page_type, visitor_hash))
            conn.commit()
    except Exception as e:
        logger.warning(f"Failed to record page view: {e}")


@contextmanager
def get_db_connection():
    """Get a database connection as a context manager."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_analytics_db_connection():
    """Get the analytics database connection as a context manager."""
    conn = sqlite3.connect(ANALYTICS_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_analytics_db():
    """Initialize the analytics database schema if it doesn't exist."""
    db_dir = Path(ANALYTICS_DB_PATH).parent
    db_dir.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(ANALYTICS_DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS page_views (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                page_type TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                visitor_hash TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pv_timestamp ON page_views(timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pv_page_type ON page_views(page_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pv_visitor ON page_views(visitor_hash)")
        conn.commit()


try:
    init_analytics_db()
except Exception as e:
    logger.warning(f"Failed to initialize analytics DB: {e}")


# Denver timezone for consistent date handling
MOUNTAIN_TZ = ZoneInfo('America/Denver')


def _current_school_year():
    """Return the school year end (graduation year for current seniors).
    School year runs Aug-Jul, so Feb 2026 -> seniors graduate 2026."""
    now = datetime.now(MOUNTAIN_TZ)
    return now.year if now.month >= 8 else now.year


def _grade_case_expression(alias='a'):
    """Return a dynamic SQL CASE expression mapping graduation_year to grade."""
    sy = _current_school_year()
    prefix = f"{alias}." if alias else ""
    return f"""CASE
                    WHEN {prefix}graduation_year = {sy} THEN '12th'
                    WHEN {prefix}graduation_year = {sy+1} THEN '11th'
                    WHEN {prefix}graduation_year = {sy+2} THEN '10th'
                    WHEN {prefix}graduation_year = {sy+3} THEN '9th'
                    ELSE NULL
                END"""


# Template helpers
def format_time(seconds):
    """Format seconds as MM:SS.ss or SS.ss"""
    if seconds is None:
        return ""
    
    if seconds >= 60:
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}:{secs:05.2f}"
    else:
        return f"{seconds:.2f}"


def format_mark(mark, is_timed=True, event_name=None):
    """Format a mark appropriately based on event type."""
    if mark is None:
        return ""
    
    if is_timed:
        return format_time(mark)
    else:
        # All field events are displayed in feet/inches
        feet = mark / 0.3048
        whole_feet = int(feet)
        inches = (feet - whole_feet) * 12
        return f"{whole_feet}' {inches:.1f}\""

# Register filters
app.jinja_env.filters['format_time'] = format_time
app.jinja_env.filters['format_mark'] = format_mark


def get_available_years():
    """Get all years that have records, ordered with newest first."""
    with get_db_connection() as conn:
        years = conn.execute("""
            SELECT DISTINCT year FROM (
                SELECT strftime('%Y', meet_date) as year FROM meets WHERE meet_date IS NOT NULL
                UNION
                SELECT season as year FROM meets WHERE meet_date IS NULL AND season IS NOT NULL
            ) ORDER BY year DESC
        """).fetchall()
    return [int(y['year']) for y in years if y['year']]


def get_current_year_filter():
    """Get the current year filter from request args, defaulting to newest year."""
    year_param = request.args.get('year', '')
    if year_param == 'all':
        return 'all'
    elif year_param:
        try:
            return int(year_param)
        except ValueError:
            pass
    # Default to newest year
    years = get_available_years()
    return years[0] if years else None


def get_ordered_years():
    """Get years in the order: newest, 'all', then rest descending."""
    years = get_available_years()
    if not years:
        return []
    newest = years[0]
    rest = years[1:] if len(years) > 1 else []
    # Return as list of tuples: (value, display_text)
    result = [(str(newest), str(newest))]
    result.append(('all', 'All Records'))
    for y in rest:
        result.append((str(y), str(y)))
    return result


def add_year_filter_to_query(base_query, year_filter, meet_alias='m', params=None):
    """Add year filter clause to a query if needed."""
    if params is None:
        params = []
    if year_filter and year_filter != 'all':
        yr = str(year_filter)
        base_query += (
            f" AND (strftime('%Y', {meet_alias}.meet_date) = ?"
            f" OR ({meet_alias}.meet_date IS NULL AND {meet_alias}.season = ?))"
        )
        params.append(yr)
        params.append(yr)
    return base_query, params


@app.context_processor
def inject_year_filter():
    """Make year filter data available to all templates."""
    years = get_available_years()
    default_year = str(years[0]) if years else ''
    return {
        'available_years': get_ordered_years(),
        'current_year': request.args.get('year', default_year),
    }


# Routes
@app.route('/')
def index():
    """Home page - team communications and information."""
    record_page_view('home')
    
    today = datetime.now(MOUNTAIN_TZ).date()

    # Load calendar events
    calendar_events = []
    # Check webapp/config first, then fall back to main config directory
    calendar_path = Path(__file__).parent / 'config' / 'calendar_events.json'
    if not calendar_path.exists():
        calendar_path = Path(__file__).parent.parent / 'config' / 'calendar_events.json'
    
    location_map = {}
    if calendar_path.exists():
        with open(calendar_path, 'r') as f:
            calendar_data = json.load(f)
            # Check if new format with locationMap
            if isinstance(calendar_data, dict) and 'locationMap' in calendar_data:
                all_events = calendar_data.get('events', [])
                location_map = calendar_data.get('locationMap', {})
            else:
                # Old format - just a list of events
                all_events = calendar_data if isinstance(calendar_data, list) else []
        
        # Filter for upcoming events only (today or future)
        for event in all_events:
            if event.get('date'):
                try:
                    # Parse date in MM/DD/YYYY format
                    event_date = datetime.strptime(event['date'], '%m/%d/%Y').date()
                    if event_date >= today:
                        calendar_events.append(event)
                except ValueError:
                    # If date parsing fails, include the event anyway
                    calendar_events.append(event)
            else:
                # No date available, include it
                calendar_events.append(event)

    # Load past meets for the current year from the database
    current_year = today.year
    with get_db_connection() as conn:
        past_meet_rows = conn.execute("""
            SELECT m.name, m.meet_date as date, COUNT(r.id) as result_count
            FROM meets m
            LEFT JOIN results r ON r.meet_id = m.id
            WHERE m.meet_date < ?
              AND (strftime('%Y', m.meet_date) = ?
                   OR (m.meet_date IS NULL AND m.season = ?))
            GROUP BY m.id
            ORDER BY m.meet_date DESC
        """, (today.isoformat(), str(current_year), str(current_year))).fetchall()
    past_meets = [{'name': r['name'], 'date': r['date'], 'result_count': r['result_count']} for r in past_meet_rows]

    return render_template('index.html', calendar_events=calendar_events, location_map=location_map,
                           past_meets=past_meets)


@app.route('/calendar')
def calendar():
    """Calendar page with meet schedule."""
    record_page_view('calendar')
    
    # Load calendar events
    calendar_path = Path(__file__).parent / 'config' / 'calendar_events.json'
    if not calendar_path.exists():
        calendar_path = Path(__file__).parent.parent / 'config' / 'calendar_events.json'
    
    # Load location map and events
    location_map = {}
    all_events = []
    
    if calendar_path.exists():
        with open(calendar_path, 'r') as f:
            calendar_data = json.load(f)
            # Check if new format with locationMap
            if isinstance(calendar_data, dict) and 'locationMap' in calendar_data:
                location_map = calendar_data.get('locationMap', {})
                all_events = calendar_data.get('events', [])
            else:
                # Old format - just a list of events
                all_events = calendar_data if isinstance(calendar_data, list) else []
    
    # Load meets configuration to get level information
    meets_path = Path(__file__).parent / 'config' / 'meets_2025.json'
    if not meets_path.exists():
        meets_path = Path(__file__).parent.parent / 'config' / 'meets_2025.json'
    
    meets_config = {}
    if meets_path.exists():
        with open(meets_path, 'r') as f:
            meets_data = json.load(f)
            for meet in meets_data.get('meets', []):
                meets_config[meet['name']] = meet
    
    # Load and organize calendar events
    events_by_month = defaultdict(lambda: defaultdict(list))
    today = datetime.now(MOUNTAIN_TZ).date()
    current_month_key = today.strftime('%Y-%m')
    
    for event in all_events:
        if event.get('date'):
            try:
                event_date = datetime.strptime(event['date'], '%m/%d/%Y')
                month_key = event_date.strftime('%Y-%m')
                
                # Only include current month and future months
                if month_key < current_month_key:
                    continue
                
                day = event_date.day
                
                # Use level from event if available, otherwise try to match with meets config
                level = event.get('level')
                if not level:
                    event_title = event.get('title', '')
                    for meet_name, meet_data in meets_config.items():
                        if meet_name.lower() in event_title.lower():
                            level = meet_data.get('level')
                            break
                
                # Normalize level to lowercase
                if level:
                    level = level.lower()
                
                event_copy = event.copy()
                event_copy['level'] = level
                event_copy['date_obj'] = event_date
                events_by_month[month_key][day].append(event_copy)
            except ValueError:
                pass
    
    # Sort months and convert to list format for template
    sorted_months = []
    for month_key in sorted(events_by_month.keys()):
        month_date = datetime.strptime(month_key, '%Y-%m')
        
        # Calculate calendar grid (start weeks on Sunday)
        cal_module.setfirstweekday(cal_module.SUNDAY)
        cal = cal_module.monthcalendar(month_date.year, month_date.month)
        
        sorted_months.append({
            'key': month_key,
            'name': month_date.strftime('%B %Y'),
            'year': month_date.year,
            'month': month_date.month,
            'calendar_weeks': cal,
            'events_by_day': dict(events_by_month[month_key]),
            'today': today
        })
    
    return render_template('calendar.html', sorted_months=sorted_months, today=today, location_map=location_map)


@app.route('/stats')
def stats():
    """Performance statistics dashboard."""
    record_page_view('stats')
    year_filter = get_current_year_filter()
    
    with get_db_connection() as conn:
        # Build year filter clause
        year_clause = ""
        year_params = []
        if year_filter and year_filter != 'all':
            yr = str(year_filter)
            year_clause = "WHERE (strftime('%Y', m.meet_date) = ? OR (m.meet_date IS NULL AND m.season = ?))"
            year_params = [yr, yr]
        
        # Get recent meets (filtered by year)
        meets_query = """
            SELECT 
                m.id,
                m.name,
                m.meet_date,
                m.venue,
                m.location,
                m.level,
                COUNT(r.id) as result_count,
                COUNT(DISTINCT r.athlete_id) as athlete_count
            FROM meets m
            LEFT JOIN results r ON m.id = r.meet_id
        """ + year_clause + """
            GROUP BY m.id, m.name, m.meet_date, m.venue, m.location, m.level
            ORDER BY m.meet_date DESC
            LIMIT 10
        """
        recent_meets = conn.execute(meets_query, year_params).fetchall()
        
        # Get athlete count (for the year)
        if year_filter and year_filter != 'all':
            yr = str(year_filter)
            athlete_count = conn.execute("""
                SELECT COUNT(DISTINCT r.athlete_id) FROM results r
                JOIN meets m ON r.meet_id = m.id
                WHERE (strftime('%Y', m.meet_date) = ? OR (m.meet_date IS NULL AND m.season = ?))
            """, [yr, yr]).fetchone()[0]
        else:
            athlete_count = conn.execute("SELECT COUNT(*) FROM athletes").fetchone()[0]
        
        # Get result count (for the year)
        if year_filter and year_filter != 'all':
            result_count = conn.execute("""
                SELECT COUNT(*) FROM results r
                JOIN meets m ON r.meet_id = m.id
                WHERE (strftime('%Y', m.meet_date) = ? OR (m.meet_date IS NULL AND m.season = ?))
            """, [yr, yr]).fetchone()[0]
        else:
            result_count = conn.execute("SELECT COUNT(*) FROM results").fetchone()[0]
        
        # Get meet count (for the year)
        if year_filter and year_filter != 'all':
            meet_count = conn.execute("""
                SELECT COUNT(*) FROM meets
                WHERE (strftime('%Y', meet_date) = ? OR (meet_date IS NULL AND season = ?))
            """, [yr, yr]).fetchone()[0]
        else:
            meet_count = conn.execute("SELECT COUNT(*) FROM meets").fetchone()[0]
        
        # Get seasons
        seasons = conn.execute("""
            SELECT DISTINCT season FROM meets 
            WHERE season IS NOT NULL 
            ORDER BY season DESC
        """).fetchall()
        
        # Get event count (for the year)
        if year_filter and year_filter != 'all':
            event_count = conn.execute("""
                SELECT COUNT(DISTINCT r.event_id) FROM results r
                JOIN meets m ON r.meet_id = m.id
                WHERE (strftime('%Y', m.meet_date) = ? OR (m.meet_date IS NULL AND m.season = ?))
            """, [yr, yr]).fetchone()[0]
        else:
            event_count = conn.execute("SELECT COUNT(DISTINCT event_id) FROM results").fetchone()[0]
        
        # Get top events by result count (for the year)
        if year_filter and year_filter != 'all':
            top_events = conn.execute("""
                SELECT e.name, COUNT(*) as result_count
                FROM results r
                JOIN events e ON r.event_id = e.id
                JOIN meets m ON r.meet_id = m.id
                WHERE (strftime('%Y', m.meet_date) = ? OR (m.meet_date IS NULL AND m.season = ?))
                GROUP BY e.id, e.name
                ORDER BY result_count DESC
                LIMIT 5
            """, [yr, yr]).fetchall()
        else:
            top_events = conn.execute("""
                SELECT e.name, COUNT(*) as result_count
                FROM results r
                JOIN events e ON r.event_id = e.id
                GROUP BY e.id, e.name
                ORDER BY result_count DESC
                LIMIT 5
            """).fetchall()
    
    return render_template('stats.html',
        stats={
            'athletes': athlete_count,
            'results': result_count,
            'meets': meet_count,
            'events': event_count
        },
        recent_meets=recent_meets,
        top_events=top_events
    )


@app.route('/athletes-2026')
def athletes_list_2026():
    """List all athletes who have results in 2026."""
    record_page_view('athletes_list_2026')
    gender_filter = request.args.get('gender', '')

    with get_db_connection() as conn:
        grade_expr = _grade_case_expression()
        query = f"""
            SELECT
                a.id,
                a.first_name || ' ' || a.last_name as name,
                a.gender,
                a.graduation_year,
                {grade_expr} as grade,
                COUNT(DISTINCT r.event_id) as event_count,
                COUNT(r.id) as result_count
            FROM athletes a
            INNER JOIN results r ON a.id = r.athlete_id
            INNER JOIN meets m ON r.meet_id = m.id
            WHERE (strftime('%Y', m.meet_date) = '2026'
                OR (m.meet_date IS NULL AND m.season = '2026'))
        """
        params = []

        if gender_filter:
            query += " AND a.gender = ?"
            params.append(gender_filter)

        query += " GROUP BY a.id ORDER BY CASE WHEN a.last_name LIKE '%Relay%' THEN 1 ELSE 0 END, a.last_name, a.first_name"
        athletes = conn.execute(query, params).fetchall()

    return render_template('athletes_list_2026.html',
        athletes=athletes,
        gender_filter=gender_filter
    )


@app.route('/athletes')
def athletes_list():
    """List all athletes."""
    record_page_view('athletes_list')
    gender_filter = request.args.get('gender', '')
    year_filter = get_current_year_filter()
    
    with get_db_connection() as conn:
        # Build the base query with year filter
        grade_expr = _grade_case_expression()
        if year_filter and year_filter != 'all':
            query = f"""
                SELECT 
                    a.id,
                    a.first_name || ' ' || a.last_name as name,
                    a.gender,
                    a.graduation_year,
                    {grade_expr} as grade,
                    COUNT(DISTINCT r.event_id) as event_count,
                    COUNT(r.id) as result_count
                FROM athletes a
                INNER JOIN results r ON a.id = r.athlete_id
                INNER JOIN meets m ON r.meet_id = m.id
                WHERE (strftime('%Y', m.meet_date) = ?
                    OR (m.meet_date IS NULL AND m.season = ?))
            """
            params = [str(year_filter), str(year_filter)]
            
            if gender_filter:
                query += " AND a.gender = ?"
                params.append(gender_filter)
            
            query += " GROUP BY a.id ORDER BY CASE WHEN a.last_name LIKE '%Relay%' THEN 1 ELSE 0 END, a.last_name, a.first_name"
            athletes = conn.execute(query, params).fetchall()
        else:
            query = f"""
                SELECT 
                    a.id,
                    a.first_name || ' ' || a.last_name as name,
                    a.gender,
                    a.graduation_year,
                    {grade_expr} as grade,
                    COUNT(DISTINCT r.event_id) as event_count,
                    COUNT(r.id) as result_count
                FROM athletes a
                LEFT JOIN results r ON a.id = r.athlete_id
            """
            
            if gender_filter:
                query += " WHERE a.gender = ?"
                query += " GROUP BY a.id ORDER BY CASE WHEN a.last_name LIKE '%Relay%' THEN 1 ELSE 0 END, a.last_name, a.first_name"
                athletes = conn.execute(query, (gender_filter,)).fetchall()
            else:
                query += " GROUP BY a.id ORDER BY CASE WHEN a.last_name LIKE '%Relay%' THEN 1 ELSE 0 END, a.last_name, a.first_name"
                athletes = conn.execute(query).fetchall()
    
    return render_template('athletes_list.html', 
        athletes=athletes,
        gender_filter=gender_filter
    )


@app.route('/athlete/<int:athlete_id>')
def athlete_stats(athlete_id):
    """Individual athlete statistics page."""
    record_page_view('athlete')  # Don't record which athlete for privacy
    with get_db_connection() as conn:
        # Get athlete info
        grade_expr = _grade_case_expression('')
        athlete_row = conn.execute(f"""
            SELECT 
                id,
                first_name || ' ' || last_name as name,
                first_name,
                last_name,
                gender,
                graduation_year,
                {grade_expr} as grade
            FROM athletes WHERE id = ?
        """, (athlete_id,)).fetchone()
        
        if not athlete_row:
            return render_template('error.html', error="Athlete not found"), 404
        
        # Convert to dict for easier template access
        athlete = dict(athlete_row)
        
        # Get season bests for this athlete (current season only)
        current_season = str(_current_school_year())
        prs = conn.execute("""
            SELECT 
                e.id as event_id,
                e.name as event_name,
                e.timed,
                e.lower_is_better,
                r.mark,
                r.mark as result_value,
                r.mark_display,
                m.meet_date,
                m.name as meet_name
            FROM results r
            JOIN events e ON r.event_id = e.id
            JOIN meets m ON r.meet_id = m.id
            WHERE r.athlete_id = ?
            AND (strftime('%Y', m.meet_date) = ? OR (m.meet_date IS NULL AND m.season = ?))
            AND r.mark = (
                SELECT CASE 
                    WHEN e.lower_is_better THEN MIN(r2.mark)
                    ELSE MAX(r2.mark)
                END
                FROM results r2
                JOIN meets m2 ON r2.meet_id = m2.id
                WHERE r2.athlete_id = r.athlete_id 
                AND r2.event_id = r.event_id
                AND (strftime('%Y', m2.meet_date) = ? OR (m2.meet_date IS NULL AND m2.season = ?))
            )
            ORDER BY e.name
        """, (athlete_id, current_season, current_season, current_season, current_season)).fetchall()

        # Get career PRs (all-time best) for this athlete
        career_pbs_raw = conn.execute("""
            SELECT 
                e.id as event_id,
                e.name as event_name,
                e.timed,
                e.lower_is_better,
                r.mark,
                r.mark_display,
                m.meet_date,
                m.name as meet_name
            FROM results r
            JOIN events e ON r.event_id = e.id
            JOIN meets m ON r.meet_id = m.id
            WHERE r.athlete_id = ?
            AND r.mark = (
                SELECT CASE 
                    WHEN e.lower_is_better THEN MIN(r2.mark)
                    ELSE MAX(r2.mark)
                END
                FROM results r2
                WHERE r2.athlete_id = r.athlete_id
                AND r2.event_id = r.event_id
            )
            GROUP BY e.id
            ORDER BY e.name
        """, (athlete_id,)).fetchall()

        # Build combined PB/SB cards (one per event)
        pb_map = {row['event_name']: dict(row) for row in career_pbs_raw}
        sb_map = {row['event_name']: dict(row) for row in prs}
        all_events = sorted(set(list(pb_map.keys()) + list(sb_map.keys())))
        pb_sb_cards = []
        for event_name in all_events:
            pb = pb_map.get(event_name)
            sb = sb_map.get(event_name)
            is_same = bool(pb and sb and abs(pb['mark'] - sb['mark']) < 0.001)
            pb_sb_cards.append({
                'event_name': event_name,
                'timed': (pb or sb)['timed'],
                'lower_is_better': (pb or sb)['lower_is_better'],
                'event_id': (pb or sb)['event_id'],
                'pb': pb,
                'sb': sb,
                'is_same': is_same,
            })
        
        # Get all results grouped by event
        results_by_event = {}
        results = conn.execute("""
            SELECT 
                e.id as event_id,
                e.name as event_name,
                e.timed,
                r.mark,
                r.mark_display,
                r.place,
                r.level,
                r.wind,
                m.meet_date,
                m.name as meet_name,
                m.season
            FROM results r
            JOIN events e ON r.event_id = e.id
            JOIN meets m ON r.meet_id = m.id
            WHERE r.athlete_id = ?
            ORDER BY m.meet_date DESC, e.name
        """, (athlete_id,)).fetchall()
        
        for result in results:
            event_name = result['event_name']
            if event_name not in results_by_event:
                results_by_event[event_name] = {
                    'event_id': result['event_id'],
                    'timed': result['timed'],
                    'results': []
                }
            results_by_event[event_name]['results'].append(result)
        
        # Group results by year
        results_by_year = {}
        events_by_year = {}
        event_ids_by_name = {}  # Map event names to IDs for chart loading
        for result in results:
            year = int(result['meet_date'].split('-')[0]) if result['meet_date'] else (int(result['season']) if result['season'] else None)
            if year:
                if year not in results_by_year:
                    results_by_year[year] = []
                    events_by_year[year] = set()
                results_by_year[year].append(result)
                events_by_year[year].add(result['event_name'])
                event_ids_by_name[result['event_name']] = result['event_id']
        
        # Sort years descending, and results within each year by date descending
        # Handle None dates by sorting them to the end
        for year in results_by_year:
            results_by_year[year].sort(key=lambda r: (r['meet_date'] is None, r['meet_date'] or ''), reverse=True)
        sorted_years = sorted(results_by_year.keys(), reverse=True)
        
        # Convert event sets to sorted lists and create event info with IDs
        events_with_ids_by_year = {}
        for year in events_by_year:
            events_by_year[year] = sorted(list(events_by_year[year]))
            events_with_ids_by_year[year] = [(e, event_ids_by_name[e]) for e in events_by_year[year]]
        
        # Count results per event per year
        event_count_by_year = {}
        for year in results_by_year:
            event_count_by_year[year] = {}
            for event in events_by_year[year]:
                event_count_by_year[year][event] = len([r for r in results_by_year[year] if r['event_name'] == event])
    
    return render_template('athlete_stats.html',
        athlete=athlete,
        prs=prs,
        pb_sb_cards=pb_sb_cards,
        results_by_event=results_by_event,
        results=results,
        results_by_year=results_by_year,
        events_by_year=events_by_year,
        events_with_ids_by_year=events_with_ids_by_year,
        event_count_by_year=event_count_by_year,
        sorted_years=sorted_years
    )


@app.route('/team-bests')
def team_bests():
    """All-time team bests by event."""
    gender = request.args.get('gender', '')
    record_page_view('team_bests', page_detail=f"all_time_{gender or 'all'}")
    
    with get_db_connection() as conn:
        # Build query for all-time team bests (no year filter)
        query = """
            SELECT 
                e.id as event_id,
                e.name as event_name,
                e.category,
                e.timed,
                a.gender,
                r.mark,
                r.mark_display,
                a.first_name || ' ' || a.last_name as athlete_name,
                a.id as athlete_id,
                COALESCE(m.meet_date, '') as meet_date,
                COALESCE(m.season, '') as season,
                m.name as meet_name
            FROM results r
            JOIN athletes a ON r.athlete_id = a.id
            JOIN events e ON r.event_id = e.id
            JOIN meets m ON r.meet_id = m.id
            WHERE 1=1
        """
        params = []
        
        if gender:
            query += " AND a.gender = ?"
            params.append(gender)
        
        query += """
            AND m.name NOT LIKE '%Arcadia%'
            AND m.name NOT LIKE '%New Balance%'
            AND r.mark = (
                SELECT CASE 
                    WHEN e.lower_is_better THEN MIN(r2.mark)
                    ELSE MAX(r2.mark)
                END
                FROM results r2
                JOIN athletes a2 ON r2.athlete_id = a2.id
                JOIN meets m2 ON r2.meet_id = m2.id
                WHERE r2.event_id = e.id
                AND a2.gender = a.gender
                AND m2.name NOT LIKE '%Arcadia%'
                AND m2.name NOT LIKE '%New Balance%'
            )
            GROUP BY e.id, a.gender
            HAVING r.id = MIN(r.id)
            ORDER BY a.gender, e.category, e.name
        """
        
        team_bests_results = conn.execute(query, params).fetchall()
        
        # Define event ordering for proper sorting
        event_order_boys_track = ['100m', '200m', '400m', '800m', '1600m', '3200m', '110m Hurdles', '300m Hurdles']
        event_order_girls_track = ['100m', '200m', '400m', '800m', '1600m', '3200m', '100m Hurdles', '300m Hurdles']
        event_order_field = ['High Jump', 'Pole Vault', 'Long Jump', 'Triple Jump', 'Shot Put', 'Discus']
        event_order_relays = ['4x100m Relay', '4x200m Relay', '4x400m Relay', '4x800m Relay']
        
        # Sort helper function
        def get_event_sort_key(result):
            event_name = result['event_name']
            category = result['category']
            gender = result['gender']
            
            if category in ['sprint', 'middle_distance', 'distance', 'hurdles']:
                if gender == 'M':
                    order_list = event_order_boys_track
                else:
                    order_list = event_order_girls_track
            elif category in ['jump', 'throw']:
                order_list = event_order_field
            elif category == 'relay':
                order_list = event_order_relays
            else:
                order_list = []
            
            try:
                return order_list.index(event_name)
            except ValueError:
                return 999
        
        # Sort results by gender, then by event order
        team_bests_results = sorted(team_bests_results, 
                                     key=lambda r: (r['gender'], get_event_sort_key(r)))
        
        # Group by gender
        boys_bests = [tb for tb in team_bests_results if tb['gender'] == 'M']
        girls_bests = [tb for tb in team_bests_results if tb['gender'] == 'F']
    
    return render_template('team_bests.html',
        boys_bests=boys_bests,
        girls_bests=girls_bests,
        team_bests=team_bests_results,
        seasons=[],  # Deprecated, kept for template compatibility
        current_season='',  # Deprecated
        current_gender=gender,
        gender=gender
    )


def _get_season_bests_data(year):
    """Shared helper to get season bests data for a given year."""
    with get_db_connection() as conn:
        query = """
            WITH RankedResults AS (
                SELECT
                    e.id as event_id,
                    e.name as event_name,
                    e.category,
                    e.timed,
                    e.lower_is_better,
                    e.is_relay,
                    a.gender,
                    a.id as athlete_id,
                    a.first_name || ' ' || a.last_name as athlete_name,
                    r.mark,
                    r.mark_display,
                    r.level,
                    m.name as meet_name,
                    m.meet_date,
                    ROW_NUMBER() OVER (
                        PARTITION BY e.id, a.id, a.gender
                        ORDER BY
                            CASE WHEN e.lower_is_better THEN r.mark END ASC,
                            CASE WHEN NOT e.lower_is_better THEN r.mark END DESC
                    ) as rn
                FROM results r
                JOIN athletes a ON r.athlete_id = a.id
                JOIN events e ON r.event_id = e.id
                JOIN meets m ON r.meet_id = m.id
                WHERE strftime('%Y', m.meet_date) = ?
            )
            SELECT *
            FROM RankedResults
            WHERE rn = 1
            ORDER BY gender, category, event_name,
                CASE WHEN lower_is_better THEN mark END ASC,
                CASE WHEN NOT lower_is_better THEN mark END DESC
        """

        all_results = conn.execute(query, [str(year)]).fetchall()

    # Category buckets
    buckets = {
        'boys_sprint': [], 'boys_middle_distance': [], 'boys_distance': [],
        'boys_hurdles': [], 'boys_relays': [], 'boys_field': [],
        'girls_sprint': [], 'girls_middle_distance': [], 'girls_distance': [],
        'girls_hurdles': [], 'girls_relays': [], 'girls_field': [],
    }

    for result in all_results:
        event_name = result['event_name']
        gender = result['gender']
        prefix = 'boys' if gender == 'M' else 'girls'

        if result['is_relay']:
            buckets[f'{prefix}_relays'].append(result)
        elif event_name in ['100m', '200m']:
            buckets[f'{prefix}_sprint'].append(result)
        elif event_name in ['400m', '800m']:
            buckets[f'{prefix}_middle_distance'].append(result)
        elif event_name in ['1600m', '3200m']:
            buckets[f'{prefix}_distance'].append(result)
        elif 'Hurdles' in event_name:
            buckets[f'{prefix}_hurdles'].append(result)
        elif result['category'] in ['jump', 'throw']:
            buckets[f'{prefix}_field'].append(result)

    # Event orderings
    event_orders = {
        'event_order_sprint': ['100m', '200m'],
        'event_order_middle': ['400m', '800m'],
        'event_order_distance': ['1600m', '3200m'],
        'event_order_hurdles_boys': ['110m Hurdles', '300m Hurdles'],
        'event_order_hurdles_girls': ['100m Hurdles', '300m Hurdles'],
        'event_order_field': ['High Jump', 'Pole Vault', 'Long Jump', 'Triple Jump', 'Shot Put', 'Discus'],
        'event_order_relays': ['4x100m Relay', '4x200m Relay', '4x400m Relay', '4x800m Relay'],
    }

    def sort_by_event_order(results, event_order):
        def get_order(result):
            try:
                return event_order.index(result['event_name'])
            except ValueError:
                return 999
        return sorted(results, key=get_order)

    def group_by_event(results):
        events = {}
        for result in results:
            en = result['event_name']
            if en not in events:
                events[en] = []
            events[en].append(result)
        return events

    def rows_to_dicts(results_by_event):
        return {en: [dict(row) for row in rows] for en, rows in results_by_event.items()}

    order_map = {
        'sprint': event_orders['event_order_sprint'],
        'middle_distance': event_orders['event_order_middle'],
        'distance': event_orders['event_order_distance'],
        'hurdles': None,  # gender-specific
        'relays': event_orders['event_order_relays'],
        'field': event_orders['event_order_field'],
    }

    template_data = dict(event_orders)
    for key, results_list in buckets.items():
        # Determine sort order
        cat = key.split('_', 1)[1]  # e.g. 'sprint', 'middle_distance'
        gender_prefix = key.split('_')[0]
        if cat == 'hurdles':
            order = event_orders[f'event_order_hurdles_{"boys" if gender_prefix == "boys" else "girls"}']
        else:
            order = order_map.get(cat, [])
        sorted_results = sort_by_event_order(results_list, order)
        template_data[key] = rows_to_dicts(group_by_event(sorted_results))

    return template_data


@app.route('/season-bests-2026')
def season_bests_2026():
    """2026 Season Bests - best result per athlete per event in 2026."""
    record_page_view('season_bests_2026')
    return render_template('season_bests_2026.html', **_get_season_bests_data(2026))


@app.route('/season-bests-2025')
def season_bests_2025():
    """2025 Season Bests - best result per athlete per event in 2025."""
    record_page_view('season_bests_2025')
    return render_template('season_bests_2025.html', **_get_season_bests_data(2025))


@app.route('/event/<event_name>')
def event_records(event_name):
    """Event records - PR list for an event."""
    record_page_view('event', page_detail=event_name)
    year_filter = get_current_year_filter()
    gender_filter = request.args.get('gender', '')
    
    with get_db_connection() as conn:
        # Get event info
        event = conn.execute("""
            SELECT * FROM events WHERE name = ?
        """, (event_name,)).fetchone()
        
        if not event:
            return render_template('error.html', error="Event not found"), 404
        
        # Check if this is a relay event
        is_relay = event['is_relay'] or 'relay' in event_name.lower()
        
        men_records = []
        women_records = []
        
        if not gender_filter or gender_filter == 'M':
            if is_relay:
                men_records = get_relay_records(conn, event['id'], 'M', year_filter, event['lower_is_better'])
            else:
                men_records = get_individual_records(conn, event['id'], 'M', year_filter, event['lower_is_better'])
        
        if not gender_filter or gender_filter == 'F':
            if is_relay:
                women_records = get_relay_records(conn, event['id'], 'F', year_filter, event['lower_is_better'])
            else:
                women_records = get_individual_records(conn, event['id'], 'F', year_filter, event['lower_is_better'])
        
        logger.info(f"Event: {event['name']}, Men's records: {len(men_records)}, Women's records: {len(women_records)}")
    
    return render_template('event_records.html',
        event=event,
        men_records=men_records,
        women_records=women_records,
        is_relay=is_relay,
        seasons=[],  # Deprecated
        current_season=''  # Deprecated
    )


# Meets excluded from all-time records (indoor / invitational-only)
EXCLUDED_FROM_RECORDS = tuple(_load_excluded_from_records())


def get_individual_records(conn, event_id, gender, year_filter, lower_is_better):
    """Get individual event records - one entry per athlete (their best)."""
    agg_func = 'MIN(r.mark)' if lower_is_better else 'MAX(r.mark)'
    
    excluded_placeholders = ','.join('?' * len(EXCLUDED_FROM_RECORDS))

    # Year filter clause for CTE - use parameterized query
    year_cte_clause = ""
    cte_params = [event_id, gender] + list(EXCLUDED_FROM_RECORDS)
    if year_filter and year_filter != 'all':
        year_cte_clause = " AND strftime('%Y', m.meet_date) = ?"
        cte_params.append(str(year_filter))
    
    query = f"""
        WITH athlete_bests AS (
            SELECT 
                a.id,
                {agg_func} as best_mark
            FROM results r
            JOIN athletes a ON r.athlete_id = a.id
            JOIN meets m ON r.meet_id = m.id
            WHERE r.event_id = ? AND a.gender = ?
              AND m.name NOT IN ({excluded_placeholders}){year_cte_clause}
            GROUP BY a.id
        )
        SELECT 
            a.id as athlete_id,
            a.first_name || ' ' || a.last_name as athlete_name,
            a.gender,
            a.graduation_year,
            r.mark,
            r.mark_display,
            r.level,
            COALESCE(m.meet_date, '') as meet_date,
            COALESCE(m.season, '') as season,
            m.name as meet_name,
            NULL as relay_members
        FROM results r
        JOIN athletes a ON r.athlete_id = a.id
        JOIN athlete_bests ab ON a.id = ab.id AND r.mark = ab.best_mark
        JOIN meets m ON r.meet_id = m.id
        WHERE r.event_id = ?
          AND m.name NOT IN ({excluded_placeholders})
    """
    
    params = cte_params + [event_id] + list(EXCLUDED_FROM_RECORDS)
    
    if year_filter and year_filter != 'all':
        query += " AND strftime('%Y', m.meet_date) = ?"
        params.append(str(year_filter))
    
    query += " ORDER BY "
    if lower_is_better:
        query += "r.mark ASC"
    else:
        query += "r.mark DESC"
    
    return conn.execute(query, params).fetchall()


def get_relay_records(conn, event_id, gender, year_filter, lower_is_better):
    """Get relay event records - show all team members for each result."""
    excluded_placeholders = ','.join('?' * len(EXCLUDED_FROM_RECORDS))

    # Year filter clause
    year_clause = ""
    params = [event_id, gender] + list(EXCLUDED_FROM_RECORDS)
    if year_filter and year_filter != 'all':
        year_clause = " AND strftime('%Y', m.meet_date) = ?"
        params.append(str(year_filter))
    
    # Get all results for this relay event
    query = f"""
        SELECT 
            r.id as result_id,
            a.id as athlete_id,
            a.first_name || ' ' || a.last_name as athlete_name,
            a.gender,
            a.graduation_year,
            r.mark,
            r.mark_display,
            r.level,
            COALESCE(m.meet_date, '') as meet_date,
            COALESCE(m.season, '') as season,
            m.name as meet_name
        FROM results r
        JOIN athletes a ON r.athlete_id = a.id
        JOIN meets m ON r.meet_id = m.id
        WHERE r.event_id = ? AND a.gender = ?
          AND m.name NOT IN ({excluded_placeholders}){year_clause}
        ORDER BY r.mark ASC
    """
    
    results = conn.execute(query, params).fetchall()
    
    # For each result, get the relay team members
    enriched_results = []
    for result in results:
        # Get relay members for this result
        members_query = """
            SELECT 
                a.first_name || ' ' || a.last_name as name,
                rm.leg_order
            FROM relay_members rm
            JOIN athletes a ON rm.athlete_id = a.id
            WHERE rm.result_id = ?
            ORDER BY rm.leg_order
        """
        members = conn.execute(members_query, (result['result_id'],)).fetchall()
        
        # Convert to dict and add relay_members
        result_dict = dict(result)
        if members:
            result_dict['relay_members'] = ', '.join([m['name'] for m in members])
        else:
            result_dict['relay_members'] = None
        
        enriched_results.append(result_dict)
    
    return enriched_results


@app.route('/events')
def events_list():
    """List all events."""
    record_page_view('events_list')
    year_filter = get_current_year_filter()
    
    with get_db_connection() as conn:
        if year_filter and year_filter != 'all':
            events = conn.execute("""
                SELECT 
                    e.id,
                    e.name,
                    e.category,
                    e.distance_meters,
                    e.timed,
                    e.lower_is_better,
                    e.is_relay,
                    e.gender_specific,
                    COUNT(CASE WHEN a.gender = 'M' THEN r.id END) as men_count,
                    COUNT(CASE WHEN a.gender = 'F' THEN r.id END) as women_count,
                    COUNT(r.id) as result_count
                FROM events e
                LEFT JOIN results r ON e.id = r.event_id
                LEFT JOIN athletes a ON r.athlete_id = a.id
                LEFT JOIN meets m ON r.meet_id = m.id
                WHERE strftime('%Y', m.meet_date) = ? OR m.meet_date IS NULL
                GROUP BY e.id
                ORDER BY e.category, e.name
            """, [str(year_filter)]).fetchall()
        else:
            events = conn.execute("""
                SELECT 
                    e.id,
                    e.name,
                    e.category,
                    e.distance_meters,
                    e.timed,
                    e.lower_is_better,
                    e.is_relay,
                    e.gender_specific,
                    COUNT(CASE WHEN a.gender = 'M' THEN r.id END) as men_count,
                    COUNT(CASE WHEN a.gender = 'F' THEN r.id END) as women_count,
                    COUNT(r.id) as result_count
                FROM events e
                LEFT JOIN results r ON e.id = r.event_id
                LEFT JOIN athletes a ON r.athlete_id = a.id
                GROUP BY e.id
                ORDER BY e.category, e.name
            """).fetchall()
    
    # Group events by category and gender
    # For gender-specific events, include only in appropriate section
    men_events_by_category = {}
    women_events_by_category = {}
    
    for event in events:
        category = event['category'].replace('_', ' ').title()
        
        # Determine which gender this event applies to
        # Check if 'gender_specific' column exists and has a value
        try:
            gender_specific = event['gender_specific'] if event['gender_specific'] else None
        except (KeyError, IndexError):
            gender_specific = None
        
        # Add to men's events if not gender-specific or specifically for men
        if not gender_specific or gender_specific == 'M':
            if category not in men_events_by_category:
                men_events_by_category[category] = []
            men_events_by_category[category].append(event)
        
        # Add to women's events if not gender-specific or specifically for women
        if not gender_specific or gender_specific == 'F':
            if category not in women_events_by_category:
                women_events_by_category[category] = []
            women_events_by_category[category].append(event)
    
    return render_template('events_list.html', 
                         men_events_by_category=men_events_by_category,
                         women_events_by_category=women_events_by_category)


# API endpoints for charts
@app.route('/api/athlete/<int:athlete_id>/progress/<int:event_id>')
def athlete_progress_api(athlete_id, event_id):
    """Get athlete progress data for charts."""
    def format_time_value(seconds):
        """Convert seconds to mm:ss.ss format for display."""
        if seconds < 60:
            return f"{seconds:.2f}"
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}:{secs:05.2f}"
    
    with get_db_connection() as conn:
        # Get all results for this athlete and event
        results = conn.execute("""
            SELECT 
                r.mark,
                r.mark_display,
                m.meet_date,
                m.name as meet_name,
                e.timed,
                e.lower_is_better
            FROM results r
            JOIN meets m ON r.meet_id = m.id
            JOIN events e ON r.event_id = e.id
            WHERE r.athlete_id = ? AND r.event_id = ?
            ORDER BY m.meet_date
        """, (athlete_id, event_id)).fetchall()
        
        if not results:
            return jsonify({'dates': [], 'values': [], 'displays': [], 'meets': [], 'is_pr': [], 'timed': True, 'event_name': ''})
        
        # Determine event type
        is_timed = results[0]['timed']
        lower_is_better = results[0]['lower_is_better']
        
        # Track progressive PRs (was this a PR at the time it was set?)
        is_pr_list = []
        best_so_far = None
        for r in results:
            if best_so_far is None:
                is_pr_list.append(True)
                best_so_far = r['mark']
            elif lower_is_better and r['mark'] < best_so_far:
                is_pr_list.append(True)
                best_so_far = r['mark']
            elif not lower_is_better and r['mark'] > best_so_far:
                is_pr_list.append(True)
                best_so_far = r['mark']
            else:
                is_pr_list.append(False)
        
        # Format display values for chart
        if is_timed:
            # For timed events, format as mm:ss.ss or ss.ss
            display_values = [format_time_value(r['mark']) for r in results]
        else:
            # For distance events, use the mark_display which shows feet/inches
            display_values = [r['mark_display'] for r in results]
        
        # Get event name for y-axis label
        event_result = conn.execute("""
            SELECT name, timed FROM events WHERE id = ?
        """, (event_id,)).fetchone()
        event_name = event_result['name'] if event_result else ""
        
        data = {
            'dates': [r['meet_date'] for r in results],
            'values': [r['mark'] for r in results],
            'displays': display_values,
            'meets': [r['meet_name'] for r in results],
            'is_pr': is_pr_list,
            'timed': is_timed,
            'event_name': event_name
        }
    
    return jsonify(data)


# Hidden Analytics Page
@app.route('/stats/<secret>')
def analytics_dashboard(secret):
    """Hidden analytics dashboard."""
    if secret != ANALYTICS_SECRET:
        return render_template('error.html', error="Page not found"), 404
    
    return render_template('analytics.html', secret=secret)


@app.route('/api/analytics/<secret>/summary')
def analytics_summary(secret):
    """Get analytics summary data."""
    if secret != ANALYTICS_SECRET:
        return jsonify({'error': 'Unauthorized'}), 403

    days = request.args.get('days', 30, type=int)
    start_date = (datetime.now(MOUNTAIN_TZ) - timedelta(days=days)).strftime('%Y-%m-%d')
    mt_offset = datetime.now(MOUNTAIN_TZ).utcoffset().total_seconds() / 3600

    with get_analytics_db_connection() as conn:
        total_views = conn.execute("""
            SELECT COUNT(*) FROM page_views WHERE DATE(timestamp) >= ?
        """, (start_date,)).fetchone()[0]

        # Unique visitor-days: distinct visitor_hash per day (hash already encodes date)
        unique_visitor_days = conn.execute("""
            SELECT COUNT(DISTINCT visitor_hash) FROM page_views WHERE DATE(timestamp) >= ?
        """, (start_date,)).fetchone()[0]

        totals = conn.execute("""
            SELECT page_type, COUNT(*) as count
            FROM page_views
            WHERE DATE(timestamp) >= ?
            GROUP BY page_type
            ORDER BY count DESC
        """, (start_date,)).fetchall()

        hourly_raw = conn.execute("""
            SELECT CAST(strftime('%H', timestamp) AS INTEGER) as hour, COUNT(*) as count
            FROM page_views
            WHERE DATE(timestamp) >= ?
            GROUP BY hour ORDER BY hour
        """, (start_date,)).fetchall()
        hourly_mt = {}
        for row in hourly_raw:
            mt_hour = int((row['hour'] + mt_offset) % 24)
            hourly_mt[mt_hour] = hourly_mt.get(mt_hour, 0) + row['count']
        hourly_adjusted = [{'hour': h, 'count': c} for h, c in sorted(hourly_mt.items())]

        dow_raw = conn.execute("""
            SELECT CAST(strftime('%w', timestamp) AS INTEGER) as dow, COUNT(*) as count
            FROM page_views
            WHERE DATE(timestamp) >= ?
            GROUP BY dow ORDER BY dow
        """, (start_date,)).fetchall()

    return jsonify({
        'period_days': days,
        'start_date': start_date,
        'total_views': total_views,
        'unique_visitor_days': unique_visitor_days,
        'by_page_type': [{'page_type': r['page_type'], 'count': r['count']} for r in totals],
        'hourly': hourly_adjusted,
        'dow': [{'dow': r['dow'], 'count': r['count']} for r in dow_raw],
    })


@app.route('/api/analytics/<secret>/trend')
def analytics_trend(secret):
    """Get analytics trend data (daily views + unique visitors)."""
    if secret != ANALYTICS_SECRET:
        return jsonify({'error': 'Unauthorized'}), 403

    days = request.args.get('days', 30, type=int)
    start_date = (datetime.now(MOUNTAIN_TZ) - timedelta(days=days)).strftime('%Y-%m-%d')

    with get_analytics_db_connection() as conn:
        views_rows = conn.execute("""
            SELECT DATE(timestamp) as date, COUNT(*) as count
            FROM page_views WHERE DATE(timestamp) >= ?
            GROUP BY DATE(timestamp) ORDER BY date
        """, (start_date,)).fetchall()

        unique_rows = conn.execute("""
            SELECT DATE(timestamp) as date, COUNT(DISTINCT visitor_hash) as count
            FROM page_views WHERE DATE(timestamp) >= ?
            GROUP BY DATE(timestamp) ORDER BY date
        """, (start_date,)).fetchall()

        by_type_rows = conn.execute("""
            SELECT DATE(timestamp) as date, page_type, COUNT(*) as count
            FROM page_views WHERE DATE(timestamp) >= ?
            GROUP BY DATE(timestamp), page_type ORDER BY date
        """, (start_date,)).fetchall()

    by_type = {}
    for row in by_type_rows:
        pt = row['page_type']
        if pt not in by_type:
            by_type[pt] = {'dates': [], 'counts': []}
        by_type[pt]['dates'].append(row['date'])
        by_type[pt]['counts'].append(row['count'])

    return jsonify({
        'total': {'dates': [r['date'] for r in views_rows], 'counts': [r['count'] for r in views_rows]},
        'unique': {'dates': [r['date'] for r in unique_rows], 'counts': [r['count'] for r in unique_rows]},
        'by_type': by_type,
    })


@app.errorhandler(404)
def not_found(error):
    return render_template('error.html', error="Page not found"), 404


@app.errorhandler(500)
def server_error(error):
    return render_template('error.html', error="Server error"), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
