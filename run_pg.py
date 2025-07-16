
from flask import Flask, render_template, request
import psycopg2
import os
import yaml
from psycopg2.extras import RealDictCursor
import math
import markdown
from markupsafe import Markup
from datetime import datetime, timedelta
import trend_tracker
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)

def connect_db():
    return psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        host="db",
        port=5432
    )

@app.route('/')
def home():
    server_filter = request.args.get('server')
    category_filter = request.args.get('category')
    channel_filter = request.args.get('channel')
    author_filter = request.args.get('author')
    keyword = request.args.get('keyword')
    tag_filter = request.args.get('tag')
    user_tag_filter = request.args.get('user_tag')
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))

    filters = []
    params = []

    if server_filter:
        filters.append("server_name = %s")
        params.append(server_filter)
    if category_filter:
        filters.append("channel_category = %s")
        params.append(category_filter)
    if channel_filter:
        filters.append("channel_name = %s")
        params.append(channel_filter)
    if author_filter:
        filters.append("author ILIKE %s")
        params.append(f"%{author_filter}%")
    if keyword:
        filters.append("tsv_content @@ plainto_tsquery('english', %s)")
        params.append(keyword)
    if tag_filter:
        filters.append("tags ILIKE %s")
        params.append(f"%{tag_filter}%")

    where_clause = " AND ".join(filters)
    if where_clause:
        where_clause = "WHERE " + where_clause

    with connect_db() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Generate category_map for filters.html
        cur.execute("SELECT DISTINCT server_name, channel_category FROM messages")
        rows = cur.fetchall()
        category_map = {}
        for row in rows:
            server = row['server_name']
            category = row['channel_category'] or '—'
            category_map.setdefault(server, set()).add(category)
        category_map = {k: sorted(v) for k, v in category_map.items()}
        
        # Build channel_map: { "Server::Category": [channels...] }
        cur.execute("SELECT DISTINCT server_name, channel_category, channel_name FROM messages")
        rows = cur.fetchall()
        channel_map = {}
        for row in rows:
            server = row['server_name']
            category = row['channel_category'] or '—'
            channel = row['channel_name']
            key = f"{server}::{category}"
            channel_map.setdefault(key, set()).add(channel)
        channel_map = {k: sorted(v) for k, v in channel_map.items()}


        # Count total messages
        count_sql = f"SELECT COUNT(*) FROM messages {where_clause}"
        cur.execute(count_sql, params)
        total_messages = cur.fetchone()['count']

        offset = (page - 1) * per_page
        query = f'''
            SELECT id, timestamp, author, content, tags, server_name, channel_name
            FROM messages
            {where_clause}
            ORDER BY timestamp DESC
            LIMIT %s OFFSET %s
        '''
        cur.execute(query, params + [per_page, offset])
        messages = cur.fetchall()

    total_pages = math.ceil(total_messages / per_page)
    return render_template(
        'index.html',
        messages=messages,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        keyword=keyword,
        category_map=category_map,
        channel_map=channel_map
    )

@app.route('/user/<username>', methods=['GET', 'POST'])
def user_profile(username):
    with connect_db() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        if request.method == 'POST':
            if 'tags' in request.form:
                tags_input = request.form.get('tags', '')
                tag_string = ', '.join([t.strip() for t in tags_input.split(',') if t.strip()])
                cur.execute("UPDATE users SET tags = %s WHERE username = %s", (tag_string, username))
                conn.commit()

            if 'notes' in request.form:
                notes_input = request.form.get('notes', '')
                cur.execute("UPDATE users SET notes = %s WHERE username = %s", (notes_input, username))
                conn.commit()

            if 'rsi_handle' in request.form:
                rsi_handle_input = request.form.get('rsi_handle', '')
                cur.execute("UPDATE users SET rsi_handle = %s WHERE username = %s", (rsi_handle_input, username))
                conn.commit()

        cur.execute("SELECT tags, notes, rsi_handle FROM users WHERE username = %s", (username,))
        user_row = cur.fetchone()
        user_tags = user_row['tags'].split(',') if user_row and user_row['tags'] else []
        user_notes = user_row['notes'] if user_row and user_row['notes'] else ''
        rsi_handle = user_row['rsi_handle'] if user_row and user_row['rsi_handle'] else ''

        # Load config.yaml and get keywords
        config_path = os.path.join(os.path.dirname(__file__), 'config', 'config.yaml')
        with open(config_path) as f:
            config = yaml.safe_load(f)

        keywords = config.get('flagged_keywords', [])

        flagged_messages = []
        if keywords:
            # Build the WHERE clause dynamically with ILIKE
            keyword_filter = ' OR '.join(["content ILIKE %s" for _ in keywords])
            query = f"""
                SELECT id, content, tags, server_name, channel_name, timestamp
                FROM messages
                WHERE author = %s AND ({keyword_filter})
                ORDER BY timestamp DESC
                LIMIT 50
            """
            # Construct the parameters: first is username, then each keyword wrapped in %%
            params = [username] + [f'%{kw}%' for kw in keywords]

            cur.execute(query, params)
            flagged_messages = cur.fetchall()

        # Known aliases (from different usernames with same RSI handle)
        cur.execute("""
            SELECT DISTINCT author FROM messages
            WHERE rsi_handle = %s AND author != %s
            LIMIT 10
        """, (username, username))
        alias_rows = cur.fetchall()
        known_aliases = [row['author'] for row in alias_rows]

        # Most frequent contacts (mentions)
        cur.execute("""
            SELECT mentioned_user AS name, COUNT(*) AS count
            FROM mentions
            WHERE author = %s
            GROUP BY mentioned_user
            ORDER BY count DESC
            LIMIT 5
        """, (username,))
        top_contacts = cur.fetchall()

        # Top servers
        cur.execute("""
            SELECT server_name AS name, COUNT(*) AS count
            FROM messages
            WHERE author = %s
            GROUP BY server_name
            ORDER BY count DESC
            LIMIT 5
        """, (username,))
        top_servers = cur.fetchall()

        # Activity in the last 30 days
        cur.execute("""
            SELECT date(timestamp) AS date, COUNT(*) AS count
            FROM messages
            WHERE author = %s AND timestamp > current_date - interval '30 days'
            GROUP BY date
            ORDER BY date ASC
        """, (username,))
        activity_data = cur.fetchall()

        rendered_notes = Markup(markdown.markdown(user_notes or ''))

        return render_template(
            "user.html",
            username=username,
            user_tags=user_tags,
            rendered_notes=rendered_notes,
            user_notes=user_notes,
            rsi_handle=rsi_handle,
            known_aliases=known_aliases,
            top_contacts=top_contacts,
            top_servers=top_servers,
            activity_data=activity_data,
            flagged_messages=flagged_messages
        )

def message_context(message_id):
    with connect_db() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Get the reference message
        cur.execute("""
            SELECT server_name, channel_category, channel_name, timestamp
            FROM messages WHERE id = %s
        """, (message_id,))
        ref_msg = cur.fetchone()

        if not ref_msg:
            return "Message not found", 404

        cur.execute("""
            SELECT * FROM messages
            WHERE server_name = %s
              AND channel_category = %s
              AND channel_name = %s
              AND timestamp BETWEEN %s - interval '5 minutes' AND %s + interval '5 minutes'
            ORDER BY timestamp ASC
        """, (
            ref_msg['server_name'],
            ref_msg['channel_category'],
            ref_msg['channel_name'],
            ref_msg['timestamp'],
            ref_msg['timestamp']
        ))

        context_msgs = cur.fetchall()
        return render_template('context.html', messages=context_msgs, ref_id=message_id)
    
from flask import render_template
from datetime import datetime, timedelta

@app.route('/dashboard')
def dashboard():
    with connect_db() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        config_path = os.path.join(os.path.dirname(__file__), 'config', 'config.yaml')
        with open(config_path) as f:
            config = yaml.safe_load(f)
        keywords = config.get('flagged_keywords', [])

        cur.execute("""
            SELECT kw.keyword, COUNT(*) AS mention_count, ROUND(AVG(score)::numeric, 2) AS sentiment_score
            FROM (
                SELECT unnest(%s::text[]) AS keyword
            ) kw
            JOIN messages m ON m.timestamp > %s AND m.content ILIKE '%%' || kw.keyword || '%%'
            GROUP BY kw.keyword
            ORDER BY mention_count DESC
            LIMIT 10;
        """, (keywords, datetime.now() - timedelta(days=1)))
        top_keywords = [row['keyword'] for row in cur.fetchall()]

        cur.execute("""
            SELECT keyword, mention_count, sentiment_score, last_seen
            FROM keyword_trends
            ORDER BY last_seen DESC
            LIMIT 20;
        """)
        trends = cur.fetchall()

        alert_tiles = [
            {"label": "Spike Alerts", "value": len(trends)},
            {"label": "Keywords Tracked", "value": len(keywords)},
            {"label": "Top Keywords Today", "value": len(top_keywords)},
            {"label": "Data Age", "value": "<24h"},
        ]

        # Default discovered trends to empty list
        discovered = []
        start_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        end_date = datetime.now().strftime('%Y-%m-%d')

    return render_template("dashboard.html",
        alert_tiles=alert_tiles,
        trends=trends,
        top_keywords=top_keywords,
        discovered=discovered,
        start_date=start_date,
        end_date=end_date
    )

@app.route('/discover_trends')
def discover_trends():
    start_str = request.args.get('start')
    end_str = request.args.get('end')
    ngram_str = request.args.get('ngram', '1')

    try:
        start_date = datetime.strptime(start_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_str, '%Y-%m-%d')
        ngram_size = int(ngram_str)
    except Exception:
        return "Invalid date or ngram value", 400

    with connect_db() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Check if trends already exist
        cur.execute("""
            SELECT COUNT(*) FROM discovered_trends
            WHERE timeframe_start = %s AND timeframe_end = %s AND ngram_size = %s
        """, (start_date, end_date, ngram_size))
        exists = cur.fetchone()['count']

    if not exists:
        trend_tracker.discover_trends(start_date, end_date, top_n=25, ngram_size=ngram_size)

    with connect_db() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT keyword, count FROM discovered_trends
            WHERE timeframe_start = %s AND timeframe_end = %s AND ngram_size = %s
            ORDER BY count DESC
        """, (start_date, end_date, ngram_size))
        discovered = cur.fetchall()

    # Repopulate other fields
    alert_tiles = []
    trends = []
    top_keywords = []

    return render_template("dashboard.html",
        alert_tiles=alert_tiles,
        trends=trends,
        top_keywords=top_keywords,
        discovered=discovered,
        start_date=start_str,
        end_date=end_str,
        ngram_size=ngram_size
    )
    
@app.route('/trends/graph')
def trend_graph():
    keyword = request.args.get('keyword')
    start_str = request.args.get('start')
    end_str = request.args.get('end')

    try:
        start_date = datetime.strptime(start_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_str, '%Y-%m-%d')
    except Exception:
        return "Invalid date format", 400

    with connect_db() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT date(timestamp) AS day, COUNT(*) AS count
            FROM messages
            WHERE content ILIKE %s AND timestamp BETWEEN %s AND %s
            GROUP BY day ORDER BY day
        """, (f"%{keyword}%", start_date, end_date))
        results = cur.fetchall()

    data = [{"date": row["day"].isoformat(), "count": row["count"]} for row in results]
    return json.dumps(data)

@app.route('/export_trends.csv')
def export_trends():
    from flask import Response
    start_str = request.args.get('start')
    end_str = request.args.get('end')
    ngram_str = request.args.get('ngram', '1')

    try:
        start_date = datetime.strptime(start_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_str, '%Y-%m-%d')
        ngram_size = int(ngram_str)
    except Exception:
        return "Invalid export parameters", 400

    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT keyword, count, timeframe_start, timeframe_end, ngram_size
            FROM discovered_trends
            WHERE timeframe_start = %s AND timeframe_end = %s AND ngram_size = %s
            ORDER BY count DESC
        """, (start_date, end_date, ngram_size))
        rows = cur.fetchall()

    def generate():
        yield 'keyword,count,timeframe_start,timeframe_end,ngram_size\n'
        for row in rows:
            yield f"{row[0]},{row[1]},{row[2]},{row[3]},{row[4]}\n"

    return Response(generate(), mimetype='text/csv', headers={"Content-Disposition": "attachment; filename=discovered_trends.csv"})
    
if __name__ == '__main__':
    app.run(debug=True)
