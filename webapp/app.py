"""
Fort Collins Track Stats Web Application
"""

import sqlite3
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from contextlib import contextmanager
from functools import wraps
from flask import Flask, render_template, request, jsonify, g

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration
import os
DATABASE_PATH = os.environ.get('DATABASE_PATH', str(Path(__file__).parent.parent / 'data' / 'generated' / 'db' / 'fct_stats.db'))

# Secret key for hidden analytics page (change this in production!)
ANALYTICS_SECRET = os.environ.get('ANALYTICS_SECRET', 'lambkin-purple-stats-2025')

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


def is_bot(user_agent):
    """Check if the user agent appears to be a bot."""
    if not user_agent:
        return True  # No user agent is suspicious
    return bool(BOT_REGEX.search(user_agent))


def record_page_view(page_type, page_detail=None):
    """Record a page view for analytics (if not a bot)."""
    user_agent = request.headers.get('User-Agent', '')
    
    if is_bot(user_agent):
        return  # Don't track bots
    
    try:
        with get_db_connection() as conn:
            conn.execute("""
                INSERT INTO page_views (page_type, page_detail)
                VALUES (?, ?)
            """, (page_type, page_detail))
            conn.commit()
    except Exception as e:
        # Don't let analytics failures break the app
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


def get_db():
    """Get database connection for request context."""
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception):
    """Close database connection at end of request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()


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
        jump_events = ['Long Jump', 'Triple Jump', 'High Jump', 'Discus', 'Shot Put', 'Pole Vault']
        if event_name and event_name in jump_events:
            # Convert meters to feet/inches for jumps
            feet = mark / 0.3048
            whole_feet = int(feet)
            inches = (feet - whole_feet) * 12
            return f"{whole_feet}' {inches:.1f}\""
        else:
            # Show other field events in meters
            return f"{mark:.2f}m"

# Register filters
app.jinja_env.filters['format_time'] = format_time
app.jinja_env.filters['format_mark'] = format_mark


def get_available_years():
    """Get all years that have records, ordered with newest first."""
    with get_db_connection() as conn:
        years = conn.execute("""
            SELECT DISTINCT strftime('%Y', meet_date) as year
            FROM meets
            WHERE meet_date IS NOT NULL
            ORDER BY year DESC
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
        base_query += f" AND strftime('%Y', {meet_alias}.meet_date) = ?"
        params.append(str(year_filter))
    return base_query, params


@app.context_processor
def inject_year_filter():
    """Make year filter data available to all templates."""
    return {
        'available_years': get_ordered_years(),
        'current_year': request.args.get('year', str(get_available_years()[0]) if get_available_years() else ''),
    }


# Routes
@app.route('/')
def index():
    """Home page - team communications and information."""
    record_page_view('home')
    
    # Load calendar events
    calendar_events = []
    calendar_path = Path(__file__).parent / 'config' / 'calendar_events.json'
    if calendar_path.exists():
        import json
        from datetime import datetime
        with open(calendar_path, 'r') as f:
            all_events = json.load(f)
        
        # Filter for upcoming events only (today or future)
        today = datetime.now().date()
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
    
    return render_template('index.html', calendar_events=calendar_events)


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
            year_clause = "WHERE strftime('%Y', m.meet_date) = ?"
            year_params = [str(year_filter)]
        
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
            athlete_count = conn.execute("""
                SELECT COUNT(DISTINCT r.athlete_id) FROM results r
                JOIN meets m ON r.meet_id = m.id
                WHERE strftime('%Y', m.meet_date) = ?
            """, [str(year_filter)]).fetchone()[0]
        else:
            athlete_count = conn.execute("SELECT COUNT(*) FROM athletes").fetchone()[0]
        
        # Get result count (for the year)
        if year_filter and year_filter != 'all':
            result_count = conn.execute("""
                SELECT COUNT(*) FROM results r
                JOIN meets m ON r.meet_id = m.id
                WHERE strftime('%Y', m.meet_date) = ?
            """, [str(year_filter)]).fetchone()[0]
        else:
            result_count = conn.execute("SELECT COUNT(*) FROM results").fetchone()[0]
        
        # Get meet count (for the year)
        if year_filter and year_filter != 'all':
            meet_count = conn.execute("""
                SELECT COUNT(*) FROM meets
                WHERE strftime('%Y', meet_date) = ?
            """, [str(year_filter)]).fetchone()[0]
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
                WHERE strftime('%Y', m.meet_date) = ?
            """, [str(year_filter)]).fetchone()[0]
        else:
            event_count = conn.execute("SELECT COUNT(DISTINCT event_id) FROM results").fetchone()[0]
        
        # Get top events by result count (for the year)
        if year_filter and year_filter != 'all':
            top_events = conn.execute("""
                SELECT e.name, COUNT(*) as result_count
                FROM results r
                JOIN events e ON r.event_id = e.id
                JOIN meets m ON r.meet_id = m.id
                WHERE strftime('%Y', m.meet_date) = ?
                GROUP BY e.id, e.name
                ORDER BY result_count DESC
                LIMIT 5
            """, [str(year_filter)]).fetchall()
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


@app.route('/athletes')
def athletes_list():
    """List all athletes."""
    record_page_view('athletes_list')
    gender_filter = request.args.get('gender', '')
    year_filter = get_current_year_filter()
    
    with get_db_connection() as conn:
        # Build the base query with year filter
        if year_filter and year_filter != 'all':
            query = """
                SELECT 
                    a.id,
                    a.first_name || ' ' || a.last_name as name,
                    a.gender,
                    a.graduation_year,
                    CASE 
                        WHEN a.graduation_year = 2026 THEN '12th'
                        WHEN a.graduation_year = 2027 THEN '11th'
                        WHEN a.graduation_year = 2028 THEN '10th'
                        WHEN a.graduation_year = 2029 THEN '9th'
                        ELSE NULL
                    END as grade,
                    COUNT(DISTINCT r.event_id) as pr_count,
                    COUNT(r.id) as result_count
                FROM athletes a
                INNER JOIN results r ON a.id = r.athlete_id
                INNER JOIN meets m ON r.meet_id = m.id
                WHERE strftime('%Y', m.meet_date) = ?
            """
            params = [str(year_filter)]
            
            if gender_filter:
                query += " AND a.gender = ?"
                params.append(gender_filter)
            
            query += " GROUP BY a.id ORDER BY a.last_name, a.first_name"
            athletes = conn.execute(query, params).fetchall()
        else:
            query = """
                SELECT 
                    a.id,
                    a.first_name || ' ' || a.last_name as name,
                    a.gender,
                    a.graduation_year,
                    CASE 
                        WHEN a.graduation_year = 2026 THEN '12th'
                        WHEN a.graduation_year = 2027 THEN '11th'
                        WHEN a.graduation_year = 2028 THEN '10th'
                        WHEN a.graduation_year = 2029 THEN '9th'
                        ELSE NULL
                    END as grade,
                    COUNT(DISTINCT r.event_id) as pr_count,
                    COUNT(r.id) as result_count
                FROM athletes a
                LEFT JOIN results r ON a.id = r.athlete_id
            """
            
            if gender_filter:
                query += " WHERE a.gender = ?"
                query += " GROUP BY a.id ORDER BY a.last_name, a.first_name"
                athletes = conn.execute(query, (gender_filter,)).fetchall()
            else:
                query += " GROUP BY a.id ORDER BY a.last_name, a.first_name"
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
        athlete_row = conn.execute("""
            SELECT 
                id,
                first_name || ' ' || last_name as name,
                first_name,
                last_name,
                gender,
                graduation_year,
                CASE 
                    WHEN graduation_year = 2026 THEN '12th'
                    WHEN graduation_year = 2027 THEN '11th'
                    WHEN graduation_year = 2028 THEN '10th'
                    WHEN graduation_year = 2029 THEN '9th'
                    ELSE NULL
                END as grade
            FROM athletes WHERE id = ?
        """, (athlete_id,)).fetchone()
        
        if not athlete_row:
            return render_template('error.html', error="Athlete not found"), 404
        
        # Convert to dict for easier template access
        athlete = dict(athlete_row)
        
        # Get PRs for this athlete
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
            AND r.mark = (
                SELECT CASE 
                    WHEN e.lower_is_better THEN MIN(r2.mark)
                    ELSE MAX(r2.mark)
                END
                FROM results r2
                WHERE r2.athlete_id = r.athlete_id 
                AND r2.event_id = r.event_id
            )
            ORDER BY e.name
        """, (athlete_id,)).fetchall()
        
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
            year = int(result['meet_date'].split('-')[0]) if result['meet_date'] else None
            if year:
                if year not in results_by_year:
                    results_by_year[year] = []
                    events_by_year[year] = set()
                results_by_year[year].append(result)
                events_by_year[year].add(result['event_name'])
                event_ids_by_name[result['event_name']] = result['event_id']
        
        # Sort years descending, and results within each year by date descending
        for year in results_by_year:
            results_by_year[year].sort(key=lambda r: r['meet_date'], reverse=True)
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
    """Team bests by event."""
    gender = request.args.get('gender', '')
    year_filter = get_current_year_filter()
    record_page_view('team_bests', page_detail=f"{year_filter or 'all'}_{gender or 'all'}")
    
    with get_db_connection() as conn:
        # Get available years (for reference, though we use the global year filter)
        years = conn.execute("""
            SELECT DISTINCT strftime('%Y', meet_date) as year FROM meets 
            WHERE meet_date IS NOT NULL 
            ORDER BY year DESC
        """).fetchall()
        
        # Build query for team bests with year filter
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
                m.meet_date,
                m.name as meet_name
            FROM results r
            JOIN athletes a ON r.athlete_id = a.id
            JOIN events e ON r.event_id = e.id
            JOIN meets m ON r.meet_id = m.id
            WHERE 1=1
        """
        params = []
        
        if year_filter and year_filter != 'all':
            query += " AND strftime('%Y', m.meet_date) = ?"
            params.append(str(year_filter))
        
        if gender:
            query += " AND a.gender = ?"
            params.append(gender)
        
        query += """
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
        """
        
        if year_filter and year_filter != 'all':
            query += " AND strftime('%Y', m2.meet_date) = ?"
            params.append(str(year_filter))
        
        query += """
            )
            GROUP BY e.id, a.gender
            ORDER BY a.gender, e.category, e.name
        """
        
        team_bests_results = conn.execute(query, params).fetchall()
        
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


@app.route('/season-bests-2025')
def season_bests_2025():
    """2025 Season Bests - best result per athlete per event in 2025."""
    record_page_view('season_bests_2025')
    
    with get_db_connection() as conn:
        # Get all 2025 results with best mark per athlete per event
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
                WHERE strftime('%Y', m.meet_date) = '2025'
            )
            SELECT *
            FROM RankedResults
            WHERE rn = 1
            ORDER BY gender, category, event_name, 
                CASE WHEN lower_is_better THEN mark END ASC,
                CASE WHEN NOT lower_is_better THEN mark END DESC
        """
        
        all_results = conn.execute(query).fetchall()
        
        # Organize results by gender and category
        boys_track = []
        boys_field = []
        boys_relays = []
        girls_track = []
        girls_field = []
        girls_relays = []
        
        for result in all_results:
            category = result['category']
            gender = result['gender']
            
            if gender == 'M':
                if result['is_relay']:
                    boys_relays.append(result)
                elif category in ['sprint', 'middle_distance', 'distance', 'hurdles']:
                    boys_track.append(result)
                else:
                    boys_field.append(result)
            else:  # F
                if result['is_relay']:
                    girls_relays.append(result)
                elif category in ['sprint', 'middle_distance', 'distance', 'hurdles']:
                    girls_track.append(result)
                else:
                    girls_field.append(result)
        
        # Get event ordering for proper sorting
        event_order_track = ['100m', '200m', '400m', '800m', '1600m', '3200m', '100m Hurdles', '110m Hurdles', '300m Hurdles']
        event_order_field = ['High Jump', 'Pole Vault', 'Long Jump', 'Triple Jump', 'Shot Put', 'Discus']
        event_order_relays = ['4x100m Relay', '4x200m Relay', '4x400m Relay', '4x800m Relay']
        
        # Sort by event order
        def sort_by_event_order(results, event_order):
            def get_order(result):
                try:
                    return event_order.index(result['event_name'])
                except ValueError:
                    return 999
            return sorted(results, key=get_order)
        
        boys_track = sort_by_event_order(boys_track, event_order_track)
        girls_track = sort_by_event_order(girls_track, event_order_track)
        boys_field = sort_by_event_order(boys_field, event_order_field)
        girls_field = sort_by_event_order(girls_field, event_order_field)
        boys_relays = sort_by_event_order(boys_relays, event_order_relays)
        girls_relays = sort_by_event_order(girls_relays, event_order_relays)
        
        # Group results by event
        def group_by_event(results):
            events = {}
            for result in results:
                event_name = result['event_name']
                if event_name not in events:
                    events[event_name] = []
                events[event_name].append(result)
            return events
        
        boys_track_by_event = group_by_event(boys_track)
        girls_track_by_event = group_by_event(girls_track)
        boys_field_by_event = group_by_event(boys_field)
        girls_field_by_event = group_by_event(girls_field)
        boys_relays_by_event = group_by_event(boys_relays)
        girls_relays_by_event = group_by_event(girls_relays)
    
    return render_template('season_bests_2025.html',
        boys_track=boys_track_by_event,
        girls_track=girls_track_by_event,
        boys_field=boys_field_by_event,
        girls_field=girls_field_by_event,
        boys_relays=boys_relays_by_event,
        girls_relays=girls_relays_by_event,
        event_order_track=event_order_track,
        event_order_field=event_order_field,
        event_order_relays=event_order_relays
    )


@app.route('/event/<event_name>')
def event_records(event_name):
    """Event records - PR list for an event."""
    record_page_view('event', page_detail=event_name)
    year_filter = get_current_year_filter()
    
    with get_db_connection() as conn:
        # Get event info
        event = conn.execute("""
            SELECT * FROM events WHERE name = ?
        """, (event_name,)).fetchone()
        
        if not event:
            return render_template('error.html', error="Event not found"), 404
        
        # Check if this is a relay event
        is_relay = event['is_relay'] or 'relay' in event_name.lower()
        
        if is_relay:
            # For relay events, get unique results with all team members
            men_records = get_relay_records(conn, event['id'], 'M', year_filter, event['lower_is_better'])
            women_records = get_relay_records(conn, event['id'], 'F', year_filter, event['lower_is_better'])
        else:
            # For individual events, get best mark per athlete
            men_records = get_individual_records(conn, event['id'], 'M', year_filter, event['lower_is_better'])
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


def get_individual_records(conn, event_id, gender, year_filter, lower_is_better):
    """Get individual event records - one entry per athlete (their best)."""
    agg_func = 'MIN(r.mark)' if lower_is_better else 'MAX(r.mark)'
    
    # Year filter clause for CTE
    year_cte_clause = ""
    if year_filter and year_filter != 'all':
        year_cte_clause = f" AND strftime('%Y', m.meet_date) = '{year_filter}'"
    
    query = f"""
        WITH athlete_bests AS (
            SELECT 
                a.id,
                {agg_func} as best_mark
            FROM results r
            JOIN athletes a ON r.athlete_id = a.id
            JOIN meets m ON r.meet_id = m.id
            WHERE r.event_id = ? AND a.gender = ?{year_cte_clause}
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
            m.meet_date,
            m.name as meet_name,
            NULL as relay_members
        FROM results r
        JOIN athletes a ON r.athlete_id = a.id
        JOIN athlete_bests ab ON a.id = ab.id AND r.mark = ab.best_mark
        JOIN meets m ON r.meet_id = m.id
        WHERE r.event_id = ?
    """
    
    params = [event_id, gender, event_id]
    
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
    # Year filter clause
    year_clause = ""
    params = [event_id, gender]
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
            m.meet_date,
            m.name as meet_name
        FROM results r
        JOIN athletes a ON r.athlete_id = a.id
        JOIN meets m ON r.meet_id = m.id
        WHERE r.event_id = ? AND a.gender = ?{year_clause}
        ORDER BY {"r.mark ASC" if lower_is_better else "r.mark DESC"}
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
                e.timed
            FROM results r
            JOIN meets m ON r.meet_id = m.id
            JOIN events e ON r.event_id = e.id
            WHERE r.athlete_id = ? AND r.event_id = ?
            ORDER BY m.meet_date
        """, (athlete_id, event_id)).fetchall()
        
        # Get PR for this event
        pr_result = conn.execute("""
            SELECT mark FROM results
            WHERE athlete_id = ? AND event_id = ?
            ORDER BY mark ASC LIMIT 1
        """, (athlete_id, event_id)).fetchone()
        
        pr_mark = pr_result['mark'] if pr_result else None
        
        # Determine if each result is a PR (for timed events, lower is better; for distance, higher is better)
        is_timed = results[0]['timed'] if results else True
        is_pr_list = []
        for r in results:
            if is_timed:
                # For timed events, PR is the minimum time
                is_pr = r['mark'] == pr_mark
            else:
                # For distance events, we need to get the maximum
                max_result = conn.execute("""
                    SELECT mark FROM results
                    WHERE athlete_id = ? AND event_id = ?
                    ORDER BY mark DESC LIMIT 1
                """, (athlete_id, event_id)).fetchone()
                max_mark = max_result['mark'] if max_result else None
                is_pr = r['mark'] == max_mark
            is_pr_list.append(is_pr)
        
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
    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    with get_db_connection() as conn:
        # Total views by page type
        totals = conn.execute("""
            SELECT page_type, COUNT(*) as count
            FROM page_views
            WHERE DATE(timestamp) >= ?
            GROUP BY page_type
            ORDER BY count DESC
        """, (start_date,)).fetchall()
        
        # Views over time (daily)
        daily = conn.execute("""
            SELECT DATE(timestamp) as date, page_type, COUNT(*) as count
            FROM page_views
            WHERE DATE(timestamp) >= ?
            GROUP BY DATE(timestamp), page_type
            ORDER BY date
        """, (start_date,)).fetchall()
        
        # Event page breakdown
        events = conn.execute("""
            SELECT page_detail, COUNT(*) as count
            FROM page_views
            WHERE page_type = 'event' AND DATE(timestamp) >= ?
            GROUP BY page_detail
            ORDER BY count DESC
        """, (start_date,)).fetchall()
        
        # Team bests breakdown
        team_bests_breakdown = conn.execute("""
            SELECT page_detail, COUNT(*) as count
            FROM page_views
            WHERE page_type = 'team_bests' AND DATE(timestamp) >= ?
            GROUP BY page_detail
            ORDER BY count DESC
        """, (start_date,)).fetchall()
        
        # Hourly distribution
        hourly = conn.execute("""
            SELECT CAST(strftime('%H', timestamp) AS INTEGER) as hour, COUNT(*) as count
            FROM page_views
            WHERE DATE(timestamp) >= ?
            GROUP BY hour
            ORDER BY hour
        """, (start_date,)).fetchall()
        
        # Total views
        total_views = conn.execute("""
            SELECT COUNT(*) FROM page_views WHERE DATE(timestamp) >= ?
        """, (start_date,)).fetchone()[0]
    
    return jsonify({
        'period_days': days,
        'start_date': start_date,
        'total_views': total_views,
        'by_page_type': [{'page_type': r['page_type'], 'count': r['count']} for r in totals],
        'daily': [{'date': r['date'], 'page_type': r['page_type'], 'count': r['count']} for r in daily],
        'events': [{'event': r['page_detail'], 'count': r['count']} for r in events],
        'team_bests': [{'detail': r['page_detail'], 'count': r['count']} for r in team_bests_breakdown],
        'hourly': [{'hour': r['hour'], 'count': r['count']} for r in hourly]
    })


@app.route('/api/analytics/<secret>/trend')
def analytics_trend(secret):
    """Get analytics trend data for charting."""
    if secret != ANALYTICS_SECRET:
        return jsonify({'error': 'Unauthorized'}), 403
    
    days = request.args.get('days', 30, type=int)
    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    with get_db_connection() as conn:
        # Get daily totals for each page type
        data = conn.execute("""
            SELECT DATE(timestamp) as date, page_type, COUNT(*) as count
            FROM page_views
            WHERE DATE(timestamp) >= ?
            GROUP BY DATE(timestamp), page_type
            ORDER BY date
        """, (start_date,)).fetchall()
    
    # Organize by page type for charting
    result = {}
    for row in data:
        page_type = row['page_type']
        if page_type not in result:
            result[page_type] = {'dates': [], 'counts': []}
        result[page_type]['dates'].append(row['date'])
        result[page_type]['counts'].append(row['count'])
    
    return jsonify(result)


@app.errorhandler(404)
def not_found(error):
    return render_template('error.html', error="Page not found"), 404


@app.errorhandler(500)
def server_error(error):
    return render_template('error.html', error="Server error"), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
