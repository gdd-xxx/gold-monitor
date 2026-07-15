import sqlite3, os, datetime, threading

from .config import DB_FILE

_local = threading.local()

def get_db():
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
    return _local.conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS gold_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            price REAL NOT NULL,
            source TEXT DEFAULT 'jdjygold',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_date ON gold_prices(date);
    """)
    conn.commit()

def insert_price(date_str, time_str, price, source="jdjygold"):
    conn = get_db()
    conn.execute(
        "INSERT INTO gold_prices (date, time, price, source) VALUES (?, ?, ?, ?)",
        (date_str, time_str, price, source),
    )
    conn.commit()

def get_today_prices():
    today = datetime.date.today().isoformat()
    conn = get_db()
    rows = conn.execute(
        "SELECT time, price FROM gold_prices WHERE date=? ORDER BY id", (today,)
    ).fetchall()
    return [{"time": r["time"], "price": r["price"]} for r in rows]

def get_latest_price():
    conn = get_db()
    row = conn.execute(
        "SELECT price, date, time FROM gold_prices ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row:
        return {"price": row["price"], "date": row["date"], "time": row["time"]}
    return None

def get_daily_prices_for_chart(days=30):
    today = datetime.date.today()
    start = (today - datetime.timedelta(days=days)).isoformat()
    conn = get_db()
    rows = conn.execute("""
        SELECT date, MIN(price) as low, MAX(price) as high,
               AVG(price) as avg_price,
               (SELECT price FROM gold_prices g2 WHERE g2.date=g1.date ORDER BY id DESC LIMIT 1) as close_price
        FROM gold_prices g1
        WHERE date >= ?
        GROUP BY date ORDER BY date
    """, (start,)).fetchall()
    return [dict(r) for r in rows]
