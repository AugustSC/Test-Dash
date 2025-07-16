import os
import json
import hashlib
import re
import psycopg2
from psycopg2.extras import execute_batch
from scoring import score_sentiment
import subprocess
from dotenv import load_dotenv
load_dotenv()

DATA_FOLDER = 'data/exports/'

def connect_db():
    return psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        host="db",
        port=5432
    )

def ensure_tables(conn):
    with conn.cursor() as cur:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS processed_files (
            filename TEXT PRIMARY KEY,
            imported_at TIMESTAMPTZ DEFAULT now()
        );
        """)
        conn.commit()

def message_id(msg):
    return msg.get('id') or hashlib.md5(
        (msg.get('timestamp', '') + msg.get('author', {}).get('name', '') + msg.get('content', '')).encode()
    ).hexdigest()

def process_json(file_path):
    print(f"📂 Importing: {file_path}")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                print(f"❌ Failed to parse {file_path}: {e}")
                return []  # Skip this file
    except Exception as e:
        print(f"⚠️ Could not open {file_path}: {e}")
        return []

    if isinstance(data, list):
        messages = data
        meta = {
            'server_name': '—',
            'channel_category': '—',
            'channel_name': '—'
        }
    else:
        messages = data.get('messages', [])
        meta = {
            'server_name': data.get('guild', {}).get('name', '—'),
            'channel_category': data.get('channel', {}).get('category', '—'),
            'channel_name': data.get('channel', {}).get('name', '—')
        }

    processed = []
    for msg in messages:
        msg_id = message_id(msg)
        author_name = msg.get('author', {}).get('name', '—')
        rsi_handle = author_name
        reactions = json.dumps(msg.get('reactions', [])) if msg.get('reactions') else None

        processed.append((
            msg_id,
            msg.get('timestamp'),
            author_name,
            msg.get('content'),
            rsi_handle,
            score_sentiment(msg.get('content', '')),
            os.path.basename(file_path),
            meta['server_name'],
            meta['channel_category'],
            meta['channel_name'],
            msg.get('author', {}).get('avatarUrl'),
            reactions,
            None
        ))

    return processed

def import_messages():
    imported = 0
    with connect_db() as conn:
        ensure_tables(conn)
        cur = conn.cursor()

        print(f"🔍 Looking for files in {DATA_FOLDER}")
        print(f"📁 Files found: {os.listdir(DATA_FOLDER)}")

        for filename in os.listdir(DATA_FOLDER):
            if not filename.endswith('.json'):
                continue

            base_filename = os.path.basename(filename)

            # Check for duplicates BEFORE parsing
            cur.execute("SELECT 1 FROM processed_files WHERE filename = %s", (base_filename,))
            if cur.fetchone():
                print(f"⏭️ Skipping already processed: {filename}")
                continue

            path = os.path.join(DATA_FOLDER, filename)
            messages = process_json(path)

            if not messages:
                print(f"⚠️ No messages found in {filename}")
                continue

            if messages:
                execute_batch(cur, '''
                    INSERT INTO messages (
                        id, timestamp, author, content, rsi_handle, score, source_file,
                        server_name, channel_category, channel_name, avatar_url, reactions, tags
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                ''', messages)

                for msg in messages:
                    author_name = msg[2]
                    rsi_handle = msg[4]
                    cur.execute('''
                        INSERT INTO users (username, nickname, rsi_handle)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (username) DO UPDATE SET
                            rsi_handle = EXCLUDED.rsi_handle
                    ''', (author_name, None, rsi_handle))

                    mention_matches = re.findall(r'@([\w\-_.]+)', msg[3] or '')
                    for mentioned in set(mention_matches):
                        cur.execute("""
                            INSERT INTO mentions (message_id, author, mentioned_user, timestamp, server_name, channel_name)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """, (msg[0], msg[2], mentioned, msg[1], msg[7], msg[9]))

                # Mark file as processed
                cur.execute("INSERT INTO processed_files (filename) VALUES (%s)", (base_filename,))
                print(f"✅ Imported {len(messages)} messages from {filename}")
                imported += len(messages)

        conn.commit()

    print(f"✅ Imported approximately {imported} messages into PostgreSQL")
    return imported

def run_trend_tracker():
    print("📈 Running trend tracker...")
    try:
        subprocess.run(["python", "trend_tracker.py"], check=True)
        print("✅ Trend tracker completed.")
    except subprocess.CalledProcessError as e:
        print("❌ Trend tracker failed:", e)

if __name__ == '__main__':
    count = import_messages()
    if count > 0:
        run_trend_tracker()
