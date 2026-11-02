import os, sqlite3, hashlib
from datetime import datetime, timezone, timedelta
DB_PATH = os.getenv("DB_PATH", "radar_slots.sqlite3")

def now():
    return datetime.now(timezone.utc).isoformat()

def db():
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c

def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS admins(id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER UNIQUE NOT NULL, label TEXT, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS wins(
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, username TEXT,
          slot TEXT NOT NULL, bet REAL NOT NULL, prize REAL NOT NULL, proof_file_id TEXT,
          proof_hash TEXT, status TEXT NOT NULL DEFAULT 'pending', fraud_flags TEXT DEFAULT '',
          created_at TEXT NOT NULL, reviewed_at TEXT, published_at TEXT);
        CREATE TABLE IF NOT EXISTS casinos(
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, url TEXT NOT NULL,
          disclosure TEXT NOT NULL DEFAULT 'Publicidade/afiliado', active INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS clicks(
          id INTEGER PRIMARY KEY AUTOINCREMENT, casino_id INTEGER NOT NULL,
          user_id INTEGER, clicked_at TEXT NOT NULL, FOREIGN KEY(casino_id) REFERENCES casinos(id));
        CREATE TABLE IF NOT EXISTS campaigns(
          id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, body TEXT NOT NULL,
          run_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'scheduled', created_by INTEGER,
          created_at TEXT NOT NULL, sent_at TEXT);
        CREATE TABLE IF NOT EXISTS operator_snapshots(
          id INTEGER PRIMARY KEY AUTOINCREMENT, operator TEXT NOT NULL, slot TEXT NOT NULL,
          metric_name TEXT NOT NULL, metric_value TEXT NOT NULL, observed_at TEXT NOT NULL,
          source TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS user_limits(user_id INTEGER PRIMARY KEY, last_submission TEXT, daily_count INTEGER DEFAULT 0, day_key TEXT);
        CREATE INDEX IF NOT EXISTS idx_wins_created ON wins(created_at);
        CREATE INDEX IF NOT EXISTS idx_wins_status ON wins(status);
        CREATE INDEX IF NOT EXISTS idx_clicks_casino ON clicks(casino_id);
        CREATE INDEX IF NOT EXISTS idx_campaigns_run ON campaigns(status, run_at);
        """)
        # Upgrade existing databases created by an earlier version.
        cols = [r[1] for r in c.execute("PRAGMA table_info(wins)").fetchall()]
        if "published_at" not in cols:
            c.execute("ALTER TABLE wins ADD COLUMN published_at TEXT")
        # Bootstrap administrators supplied through env
        ids = [x.strip() for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
        for value in ids:
            try:
                c.execute("INSERT OR IGNORE INTO admins(telegram_id,label,created_at) VALUES(?,?,?)",
                          (int(value), "Administrador inicial", now()))
            except ValueError:
                pass

def is_admin(uid):
    with db() as c:
        return c.execute("SELECT 1 FROM admins WHERE telegram_id=?", (uid,)).fetchone() is not None

def admins():
    with db() as c:
        return [dict(r) for r in c.execute("SELECT * FROM admins ORDER BY created_at")]

def add_admin(uid, label="Administrador"):
    with db() as c:
        c.execute("INSERT OR IGNORE INTO admins(telegram_id,label,created_at) VALUES(?,?,?)", (uid,label,now()))
        return c.total_changes > 0

def remove_admin(uid):
    with db() as c:
        c.execute("DELETE FROM admins WHERE telegram_id=?", (uid,))
        return c.total_changes > 0

def check_submission(uid, slot, bet, prize, proof_file_id):
    """Return list of review flags. No automatic public accusation or auto-approval."""
    flags = []
    current = datetime.now(timezone.utc)
    day = current.date().isoformat()
    with db() as c:
        row = c.execute("SELECT * FROM user_limits WHERE user_id=?", (uid,)).fetchone()
        if row and row["day_key"] == day and row["daily_count"] >= 5:
            flags.append("limite_diario_excedido")
        if row and row["last_submission"]:
            last = datetime.fromisoformat(row["last_submission"])
            if (current - last).total_seconds() < 90:
                flags.append("envio_muito_rapido")
        if not proof_file_id:
            flags.append("sem_comprovante")
        if bet <= 0 or prize <= 0:
            flags.append("valor_invalido")
        if bet > 0 and prize / bet > 10000:
            flags.append("multiplicador_extremo")
        duplicate = c.execute(
            "SELECT id FROM wins WHERE user_id=? AND lower(slot)=lower(?) AND bet=? AND prize=? AND created_at >= ?",
            (uid, slot, bet, prize, (current - timedelta(days=30)).isoformat())
        ).fetchone()
        if duplicate:
            flags.append("possivel_duplicado")
        c.execute("""INSERT INTO user_limits(user_id,last_submission,daily_count,day_key)
          VALUES(?,?,1,?) ON CONFLICT(user_id) DO UPDATE SET
          daily_count=CASE WHEN day_key=excluded.day_key THEN daily_count+1 ELSE 1 END,
          day_key=excluded.day_key,last_submission=excluded.last_submission""",
          (uid,current.isoformat(),day))
    return flags

def add_win(uid, username, slot, bet, prize, proof_file_id, flags):
    ph = hashlib.sha256(proof_file_id.encode()).hexdigest() if proof_file_id else None
    with db() as c:
        if ph:
            dup = c.execute("SELECT id FROM wins WHERE proof_hash=? AND created_at >= ?",
                            (ph,(datetime.now(timezone.utc)-timedelta(days=30)).isoformat())).fetchone()
            if dup:
                flags = list(flags) + ["comprovante_reutilizado"]
        cur = c.execute("""INSERT INTO wins(user_id,username,slot,bet,prize,proof_file_id,proof_hash,status,fraud_flags,created_at)
          VALUES(?,?,?,?,?,?,?,'pending',?,?)""",
          (uid,username,slot,bet,prize,proof_file_id,ph,",".join(flags),now()))
        return cur.lastrowid

def get_win(wid):
    with db() as c:
        r=c.execute("SELECT * FROM wins WHERE id=?",(wid,)).fetchone()
        return dict(r) if r else None

def pending_wins(limit=100):
    with db() as c:
        return [dict(r) for r in c.execute("SELECT * FROM wins WHERE status='pending' ORDER BY created_at LIMIT ?",(limit,))]

def review_win(wid, status):
    with db() as c:
        r=c.execute("SELECT * FROM wins WHERE id=? AND status='pending'",(wid,)).fetchone()
        if not r: return None
        c.execute("UPDATE wins SET status=?,reviewed_at=? WHERE id=?",(status,now(),wid))
        return dict(r)

def radar(period="week", limit=10):
    delta={"day":1,"week":7,"month":30}.get(period,7)
    since=(datetime.now(timezone.utc)-timedelta(days=delta)).isoformat()
    with db() as c:
        return [dict(r) for r in c.execute("""
          SELECT slot,COUNT(*) wins,SUM(prize) total_prize
          FROM wins WHERE status='approved' AND created_at>=?
          GROUP BY lower(slot) ORDER BY wins DESC,total_prize DESC LIMIT ?""",(since,limit))]

def recent_wins(limit=10):
    with db() as c:
        return [dict(r) for r in c.execute("SELECT * FROM wins WHERE status='approved' ORDER BY created_at DESC LIMIT ?",(limit,))]

def add_casino(name,url,disclosure):
    with db() as c:
        cur=c.execute("INSERT INTO casinos(name,url,disclosure,created_at) VALUES(?,?,?,?)",(name,url,disclosure,now()))
        return cur.lastrowid

def casinos(active_only=True):
    with db() as c:
        q="SELECT * FROM casinos"
        if active_only: q += " WHERE active=1"
        return [dict(r) for r in c.execute(q+" ORDER BY name")]

def delete_casino(cid):
    with db() as c:
        c.execute("DELETE FROM casinos WHERE id=?",(cid,))
        return c.total_changes>0

def add_click(cid,uid=None):
    with db() as c:
        c.execute("INSERT INTO clicks(casino_id,user_id,clicked_at) VALUES(?,?,?)",(cid,uid,now()))

def click_stats():
    with db() as c:
        return [dict(r) for r in c.execute("""SELECT ca.id,ca.name,COUNT(cl.id) clicks,
          COUNT(DISTINCT cl.user_id) unique_users FROM casinos ca LEFT JOIN clicks cl ON cl.casino_id=ca.id
          GROUP BY ca.id ORDER BY clicks DESC""")]

def add_campaign(title,body,run_at,admin_id):
    with db() as c:
        cur=c.execute("INSERT INTO campaigns(title,body,run_at,created_by,created_at) VALUES(?,?,?,?,?)",(title,body,run_at,admin_id,now()))
        return cur.lastrowid

def due_campaigns():
    with db() as c:
        return [dict(r) for r in c.execute("SELECT * FROM campaigns WHERE status='scheduled' AND run_at<=?",(now(),))]

def mark_campaign(cid,status="sent"):
    with db() as c:
        c.execute("UPDATE campaigns SET status=?,sent_at=? WHERE id=?",(status,now(),cid))

def campaign_list():
    with db() as c:
        return [dict(r) for r in c.execute("SELECT * FROM campaigns ORDER BY run_at DESC LIMIT 100")]

def stats():
    with db() as c:
        return {
          "users":c.execute("SELECT COUNT(DISTINCT user_id) FROM wins").fetchone()[0],
          "approved":c.execute("SELECT COUNT(*) FROM wins WHERE status='approved'").fetchone()[0],
          "pending":c.execute("SELECT COUNT(*) FROM wins WHERE status='pending'").fetchone()[0],
          "rejected":c.execute("SELECT COUNT(*) FROM wins WHERE status='rejected'").fetchone()[0],
          "clicks":c.execute("SELECT COUNT(*) FROM clicks").fetchone()[0],
          "campaigns":c.execute("SELECT COUNT(*) FROM campaigns WHERE status='scheduled'").fetchone()[0],
        }

def save_operator_rows(rows, source="official_api"):
    with db() as c:
        for r in rows:
            c.execute("""INSERT INTO operator_snapshots(operator,slot,metric_name,metric_value,observed_at,source)
              VALUES(?,?,?,?,?,?)""",(r["operator"],r["slot"],r["metric_name"],str(r["metric_value"]),now(),source))

def operator_rows(limit=30):
    with db() as c:
        return [dict(r) for r in c.execute("SELECT * FROM operator_snapshots ORDER BY observed_at DESC LIMIT ?",(limit,))]


def unpublished_wins(limit=50):
    with db() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM wins WHERE status='approved' AND published_at IS NULL ORDER BY reviewed_at LIMIT ?", (limit,)
        )]

def mark_win_published(wid):
    with db() as c:
        c.execute("UPDATE wins SET published_at=? WHERE id=? AND published_at IS NULL", (now(), wid))
