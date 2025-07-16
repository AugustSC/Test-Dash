
import psycopg2

def wipe():
    try:
        with psycopg2.connect(
            dbname="starspy",
            user="staruser",
            password="supersecret",
            host="localhost",
            port=5432
        ) as conn:
            with conn.cursor() as cur:
                cur.execute('DROP TABLE IF EXISTS messages')
                cur.execute('DROP TABLE IF EXISTS users')
                cur.execute('DROP TABLE IF EXISTS processed_files')
                conn.commit()
                print("✅ PostgreSQL database wiped. Run importer_pg_tracked.py to reimport messages.")
    except Exception as e:
        print(f"❌ Error wiping PostgreSQL database: {e}")

if __name__ == '__main__':
    wipe()
