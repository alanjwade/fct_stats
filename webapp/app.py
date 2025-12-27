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
DATABASE_PATH = os.environ.get('DATABASE_PATH', str(Path(__file__).parent.parent / 'data' / 'fct_stats.db'))

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


# Routes
@app.route('/')
def index():
    """Dashboard / home page."""
    record_page_view('home')
    with get_db_connection() as conn:
        # Get recent meets
        recent_meets = conn.execute("""
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
            GROUP BY m.id, m.name, m.meet_date, m.venue, m.location, m.level
            ORDER BY m.meet_date DESC
            LIMIT 10
        """).fetchall()
        
        # Get athlete count
        athlete_count = conn.execute("SELECT COUNT(*) FROM athletes").fetchone()[0]
        
        # Get result count
        result_count = conn.execute("SELECT COUNT(*) FROM results").fetchone()[0]
        
        # Get meet count
        meet_count = conn.execute("SELECT COUNT(*) FROM meets").fetchone()[0]
        
        # Get seasons
        seasons = conn.execute("""
            SELECT DISTINCT season FROM meets 
            WHERE season IS NOT NULL 
            ORDER BY season DESC
        """).fetchall()
        
        # Get event count
        event_count = conn.execute("SELECT COUNT(DISTINCT event_id) FROM results").fetchone()[0]
        
        # Get top events by result count
        top_events = conn.execute("""
            SELECT e.name, COUNT(*) as result_count
            FROM results r
            JOIN events e ON r.event_id = e.id
            GROUP BY e.id, e.name
            ORDER BY result_count DESC
            LIMIT 5
        """).fetchall()
    
    return render_template('index.html',
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
    
    with get_db_connection() as conn:
        query = """
            SELECT 
                a.id,
                a.first_name || ' ' || a.last_name as name,
                a.gender,
                a.graduation_year,
                CASE 
                    WHEN a.graduation_year >= 2026 THEN '9th'
                    WHEN a.graduation_year >= 2027 THEN '10th'
                    WHEN a.graduation_year >= 2028 THEN '11th'
                    WHEN a.graduation_year >= 2029 THEN '12th'
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
            ORDER BY e.name, m.meet_date DESC
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
    
    return render_template('athlete_stats.html',
        athlete=athlete,
        prs=prs,
        results_by_event=results_by_event,
        results=results
    )


@app.route('/team-bests')
def team_bests():
    """Team bests by event."""
    season = request.args.get('season', '')
    gender = request.args.get('gender', '')
    record_page_view('team_bests', page_detail=f"{season or 'all'}_{gender or 'all'}")
    
    with get_db_connection() as conn:
        # Get available seasons
        seasons = conn.execute("""
            SELECT DISTINCT season FROM meets 
            WHERE season IS NOT NULL 
            ORDER BY season DESC
        """).fetchall()
        
        # Build query for team bests
        if season:
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
                WHERE m.season = ?
            """
            params = [season]
        else:
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
        
        if season:
            query += " AND m2.season = ?"
            params.append(season)
        
        query += """
            )
            GROUP BY e.id, a.gender
            ORDER BY a.gender, e.category, e.name
        """
        
        team_bests = conn.execute(query, params).fetchall()
        
        # Group by gender
        boys_bests = [tb for tb in team_bests if tb['gender'] == 'M']
        girls_bests = [tb for tb in team_bests if tb['gender'] == 'F']
    
    return render_template('team_bests.html',
        boys_bests=boys_bests,
        girls_bests=girls_bests,
        team_bests=team_bests,
        seasons=[s['season'] for s in seasons],
        current_season=season,
        current_gender=gender,
        gender=gender
    )


@app.route('/event/<event_name>')
def event_records(event_name):
    """Event records - PR list for an event."""
    record_page_view('event', page_detail=event_name)
    season = request.args.get('season', '')
    
    with get_db_connection() as conn:
        # Get event info
        event = conn.execute("""
            SELECT * FROM events WHERE name = ?
        """, (event_name,)).fetchone()
        
        if not event:
            return render_template('error.html', error="Event not found"), 404
        
        # Get available seasons
        seasons = conn.execute("""
            SELECT DISTINCT season FROM meets 
            WHERE season IS NOT NULL 
            ORDER BY season DESC
        """).fetchall()
        
        # Build PR query - one entry per athlete (their best)
        # Use a CTE to get the best mark for each athlete in this event
        agg_func = 'MIN(r.mark)' if event['lower_is_better'] else 'MAX(r.mark)'
        
        # Query for men's records
        men_query = f"""
            WITH athlete_bests AS (
                SELECT 
                    a.id,
                    {agg_func} as best_mark
                FROM results r
                JOIN athletes a ON r.athlete_id = a.id
                WHERE r.event_id = ? AND a.gender = 'M'
        """
        
        men_params = [event['id']]
        
        men_query += " GROUP BY a.id)"
        
        men_query += """
            SELECT 
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
            JOIN athlete_bests ab ON a.id = ab.id AND r.mark = ab.best_mark
            JOIN meets m ON r.meet_id = m.id
            WHERE r.event_id = ?
        """
        
        men_params.append(event['id'])
        
        if season:
            men_query += " AND m.season = ?"
            men_params.append(season)
        
        men_query += " ORDER BY "
        if event['lower_is_better']:
            men_query += "r.mark ASC"
        else:
            men_query += "r.mark DESC"
        
        men_records = conn.execute(men_query, men_params).fetchall()
        
        # Query for women's records
        women_query = f"""
            WITH athlete_bests AS (
                SELECT 
                    a.id,
                    {agg_func} as best_mark
                FROM results r
                JOIN athletes a ON r.athlete_id = a.id
                WHERE r.event_id = ? AND a.gender = 'F'
        """
        
        women_params = [event['id']]
        
        women_query += " GROUP BY a.id)"
        
        women_query += """
            SELECT 
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
            JOIN athlete_bests ab ON a.id = ab.id AND r.mark = ab.best_mark
            JOIN meets m ON r.meet_id = m.id
            WHERE r.event_id = ?
        """
        
        women_params.append(event['id'])
        
        if season:
            women_query += " AND m.season = ?"
            women_params.append(season)
        
        women_query += " ORDER BY "
        if event['lower_is_better']:
            women_query += "r.mark ASC"
        else:
            women_query += "r.mark DESC"
        
        women_records = conn.execute(women_query, women_params).fetchall()
        
        logger.info(f"Event: {event['name']}, Men's records: {len(men_records)}, Women's records: {len(women_records)}")
    
    return render_template('event_records.html',
        event=event,
        men_records=men_records,
        women_records=women_records,
        seasons=[s['season'] for s in seasons],
        current_season=season
    )


@app.route('/events')
def events_list():
    """List all events."""
    record_page_view('events_list')
    with get_db_connection() as conn:
        events = conn.execute("""
            SELECT 
                e.*,
                COUNT(CASE WHEN a.gender = 'M' THEN r.id END) as men_count,
                COUNT(CASE WHEN a.gender = 'F' THEN r.id END) as women_count,
                COUNT(r.id) as result_count
            FROM events e
            LEFT JOIN results r ON e.id = r.event_id
            LEFT JOIN athletes a ON r.athlete_id = a.id
            GROUP BY e.id
            ORDER BY e.category, e.name
        """).fetchall()
    
    # Group events by category
    events_by_category = {}
    for event in events:
        category = event['category'].replace('_', ' ').title()
        if category not in events_by_category:
            events_by_category[category] = []
        events_by_category[category].append(event)
    
    return render_template('events_list.html', events_by_category=events_by_category)


# API endpoints for charts
@app.route('/api/athlete/<int:athlete_id>/progress/<int:event_id>')
def athlete_progress_api(athlete_id, event_id):
    """Get athlete progress data for charts."""
    with get_db_connection() as conn:
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
        
        data = {
            'dates': [r['meet_date'] for r in results],
            'marks': [r['mark'] for r in results],
            'displays': [r['mark_display'] for r in results],
            'meets': [r['meet_name'] for r in results],
            'timed': results[0]['timed'] if results else True
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
