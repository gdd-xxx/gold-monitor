import sqlite3, os, datetime

from .config import DB_FILE

def _get_conn():
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with _get_conn() as conn:
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

            CREATE TABLE IF NOT EXISTS market_prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_type TEXT NOT NULL,
                code TEXT NOT NULL,
                name TEXT DEFAULT '',
                price REAL NOT NULL,
                change_pct REAL DEFAULT 0,
                extra_json TEXT DEFAULT '{}',
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_market_code ON market_prices(code, date);
        """)
        conn.commit()

def insert_price(date_str, time_str, price, source="jdjygold"):
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO gold_prices (date, time, price, source) VALUES (?, ?, ?, ?)",
            (date_str, time_str, price, source),
        )
        conn.commit()

def get_today_prices():
    today = datetime.date.today().isoformat()
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT time, price FROM gold_prices WHERE date=? ORDER BY id", (today,)
        ).fetchall()
    return [{"time": r["time"], "price": r["price"]} for r in rows]

def get_latest_price():
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT price, date, time FROM gold_prices ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if row:
        return {"price": row["price"], "date": row["date"], "time": row["time"]}
    return None

def get_daily_prices_for_chart(days=30):
    today = datetime.date.today()
    start = (today - datetime.timedelta(days=days)).isoformat()
    with _get_conn() as conn:
        rows = conn.execute("""
            SELECT date, MIN(price) as low, MAX(price) as high,
                   AVG(price) as avg_price,
                   (SELECT price FROM gold_prices g2 WHERE g2.date=g1.date ORDER BY id DESC LIMIT 1) as close_price
            FROM gold_prices g1
            WHERE date >= ?
            GROUP BY date ORDER BY date
        """, (start,)).fetchall()
    return [dict(r) for r in rows]

def insert_market_price(asset_type, code, name, price, change_pct, extra_json="{}"):
    now = datetime.datetime.now()
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO market_prices (asset_type, code, name, price, change_pct, extra_json, date, time) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (asset_type, code, name, price, change_pct, extra_json, now.date().isoformat(), now.strftime("%H:%M:%S")),
        )
        conn.commit()

def get_latest_market_price(code):
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT price, change_pct, name, date, time FROM market_prices WHERE code=? ORDER BY id DESC LIMIT 1",
            (code,),
        ).fetchone()
    if row:
        return {"price": row["price"], "change_pct": row["change_pct"], "name": row["name"], "date": row["date"], "time": row["time"]}
    return None

def get_today_market_prices(code):
    today = datetime.date.today().isoformat()
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT time, price, change_pct FROM market_prices WHERE code=? AND date=? ORDER BY id",
            (code, today),
        ).fetchall()
    return [{"time": r["time"], "price": r["price"], "change_pct": r["change_pct"]} for r in rows]

def get_all_latest_market_prices(codes):
    if not codes:
        return {}
    result = {}
    with _get_conn() as conn:
        for code in codes:
            row = conn.execute(
                "SELECT price, change_pct, name, date, time FROM market_prices WHERE code=? ORDER BY id DESC LIMIT 1",
                (code,),
            ).fetchone()
            if row:
                result[code] = {"price": row["price"], "change_pct": row["change_pct"], "name": row["name"], "date": row["date"], "time": row["time"]}
    return result
