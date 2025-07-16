import psycopg2
import re
import os
from datetime import datetime
from collections import Counter
import string
import sys
from dotenv import load_dotenv
load_dotenv()

def connect_db():
    return psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        host="db",
        port=5432
    )

def load_stopwords():
    path = os.path.join(os.path.dirname(__file__), 'config', 'stopwords.txt')
    with open(path, 'r', encoding='utf-8') as f:
        return set(word.strip().lower() for word in f if word.strip())

STOPWORDS = load_stopwords()

def clean_and_tokenise(text, n=1):
    if not text:
        return []

    text = text.lower()
    text = text.translate(str.maketrans('', '', string.punctuation))
    words = re.findall(r'\b\w+\b', text)
    words = [w for w in words if w not in STOPWORDS and len(w) > 2]

    if n == 1:
        return words

    phrases = []
    for i in range(len(words) - n + 1):
        phrase_words = words[i:i+n]
        stopword_ratio = sum(1 for w in phrase_words if w in STOPWORDS) / n
        has_duplicates = len(set(phrase_words)) < len(phrase_words)

        if stopword_ratio < 0.5 and not has_duplicates:
            phrases.append(' '.join(phrase_words))

    return phrases

#def clean_and_tokenise(text, n=1):
#    if not text:
#        return []
#    text = text.lower()
#    text = text.translate(str.maketrans('', '', string.punctuation))
#    words = re.findall(r'\b\w+\b', text)
#    words = [w for w in words if w not in STOPWORDS and len(w) > 2]
#    if n == 1:
#        return words
#
#    phrases = []
#    for i in range(len(words) - n + 1):
#        phrase_words = words[i:i+n]
#        stopword_ratio = sum(1 for w in phrase_words if w in STOPWORDS) / n
#        has_duplicates = len(set(phrase_words)) < len(phrase_words)
#
#        if stopword_ratio < 0.5 and not has_duplicates:
#            phrases.append(' '.join(phrase_words))
#
#    return phrases

def discover_trends(start_date, end_date, top_n=25, ngram_size=1):
    with connect_db() as conn:
        cur = conn.cursor()

        # Step 1: Pull message content in timeframe
        cur.execute("""
            SELECT content FROM messages
            WHERE timestamp BETWEEN %s AND %s
        """, (start_date, end_date))
        rows = cur.fetchall()

        # Step 2: Tokenise
        all_tokens = []
        for row in rows:
            content = row[0]
            tokens = clean_and_tokenise(content, n=ngram_size)
            all_tokens.extend(tokens)

        # Step 3: Count frequency
        counter = Counter(all_tokens)
        top_keywords = counter.most_common(top_n)

        # Step 4: Create or clear table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS discovered_trends (
                keyword TEXT,
                count INT,
                timeframe_start TIMESTAMP,
                timeframe_end TIMESTAMP,
                ngram_size INT
            )
        """)
        cur.execute("""
            DELETE FROM discovered_trends
            WHERE timeframe_start = %s AND timeframe_end = %s AND ngram_size = %s
        """, (start_date, end_date, ngram_size))

        # Step 5: Insert results
        cur.executemany("""
            INSERT INTO discovered_trends (keyword, count, timeframe_start, timeframe_end, ngram_size)
            VALUES (%s, %s, %s, %s, %s)
        """, [(kw, ct, start_date, end_date, ngram_size) for kw, ct in top_keywords])

        conn.commit()
        print(f"✅ Discovered {len(top_keywords)} trending {'phrases' if ngram_size > 1 else 'keywords'} between {start_date} and {end_date}")

if __name__ == '__main__':
    if len(sys.argv) not in [3, 4, 5]:
        print("Usage: python trend_tracker.py YYYY-MM-DD YYYY-MM-DD [TOP_N] [NGRAM_SIZE]")
    else:
        start = datetime.strptime(sys.argv[1], '%Y-%m-%d')
        end = datetime.strptime(sys.argv[2], '%Y-%m-%d')
        top_n = int(sys.argv[3]) if len(sys.argv) >= 4 else 25
        ngram_size = int(sys.argv[4]) if len(sys.argv) == 5 else 1
        discover_trends(start, end, top_n=top_n, ngram_size=ngram_size)
