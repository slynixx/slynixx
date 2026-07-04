"""SQLite storage layer for Workbay.

All money values are stored as integer cents to avoid floating point
drift.  The database lives in %APPDATA%\\Workbay\\workbay.db (overridable
with WORKBAY_DB_DIR / WORKBAY_DB) -- never next to the program, because a
onefile exe unpacks into a temp folder that is wiped on exit.
"""

import os
import re
import sqlite3
import threading
import time

_SPLIT_RE = re.compile(r"[,;\n]")

SCHEMA = """
CREATE TABLE IF NOT EXISTS workshops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    labour_rate_cents INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'workshop')),
    workshop_id INTEGER REFERENCES workshops(id) ON DELETE CASCADE,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS vehicles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workshop_id INTEGER NOT NULL REFERENCES workshops(id) ON DELETE CASCADE,
    registration TEXT NOT NULL,
    year INTEGER,
    make TEXT NOT NULL DEFAULT '',
    customer TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    job TEXT NOT NULL DEFAULT '',
    labour_hours REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'done')),
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS repair_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0,
    position INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS parts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    part_number TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    supplier TEXT NOT NULL DEFAULT '',
    cost_cents INTEGER NOT NULL DEFAULT 0,
    discount_pct REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'Ordered'
        CHECK (status IN ('Ordered', 'Arrived', 'Fitted')),
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_vehicles_reg ON vehicles(registration);
CREATE INDEX IF NOT EXISTS idx_vehicles_workshop ON vehicles(workshop_id);
CREATE INDEX IF NOT EXISTS idx_items_vehicle ON repair_items(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_parts_vehicle ON parts(vehicle_id);
"""

PART_STATUSES = ("Ordered", "Arrived", "Fitted")


def data_dir():
    """Folder that holds the database, client config and error log."""
    explicit = os.environ.get("WORKBAY_DB_DIR")
    if explicit:
        path = explicit
    else:
        appdata = os.environ.get("APPDATA")
        if appdata:
            path = os.path.join(appdata, "Workbay")
        else:
            path = os.path.join(
                os.path.expanduser("~"), ".local", "share", "Workbay"
            )
    os.makedirs(path, exist_ok=True)
    return path


def db_path():
    explicit = os.environ.get("WORKBAY_DB")
    if explicit:
        folder = os.path.dirname(os.path.abspath(explicit))
        if folder:
            os.makedirs(folder, exist_ok=True)
        return explicit
    return os.path.join(data_dir(), "workbay.db")


def split_items(text):
    """Split free text on commas / semicolons / newlines into clean,
    capitalised repair items."""
    items = []
    for raw in _SPLIT_RE.split(text or ""):
        cleaned = " ".join(raw.split())
        if cleaned:
            items.append(cleaned[:1].upper() + cleaned[1:])
    return items


class Database:
    """Thread-safe wrapper around one SQLite connection.

    http.server handles each request on its own thread, so every public
    method takes the lock around its transaction.
    """

    def __init__(self, path=None):
        self.path = path or db_path()
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        with self._lock, self._conn:
            self._conn.executescript(SCHEMA)

    def close(self):
        with self._lock:
            self._conn.close()

    # ------------------------------------------------------------- users

    def get_user_by_username(self, username):
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()
        return dict(row) if row else None

    def get_user(self, user_id):
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        return dict(row) if row else None

    def create_admin_if_missing(self, username, password_hash):
        with self._lock, self._conn:
            existing = self._conn.execute(
                "SELECT 1 FROM users WHERE role = 'admin' LIMIT 1"
            ).fetchone()
            if existing:
                return False
            self._conn.execute(
                "INSERT INTO users (username, password_hash, role, created_at)"
                " VALUES (?, ?, 'admin', ?)",
                (username, password_hash, time.time()),
            )
        return True

    def set_password(self, user_id, password_hash):
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (password_hash, user_id),
            )

    # --------------------------------------------------------- workshops

    def create_workshop_with_user(self, name, username, password_hash):
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT INTO workshops (name, labour_rate_cents, created_at)"
                " VALUES (?, 0, ?)",
                (name, time.time()),
            )
            workshop_id = cur.lastrowid
            self._conn.execute(
                "INSERT INTO users"
                " (username, password_hash, role, workshop_id, created_at)"
                " VALUES (?, ?, 'workshop', ?, ?)",
                (username, password_hash, workshop_id, time.time()),
            )
        return workshop_id

    def get_workshop(self, workshop_id):
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM workshops WHERE id = ?", (workshop_id,)
            ).fetchone()
        return dict(row) if row else None

    def update_workshop(self, workshop_id, name=None, labour_rate_cents=None):
        with self._lock, self._conn:
            if name is not None:
                self._conn.execute(
                    "UPDATE workshops SET name = ? WHERE id = ?",
                    (name, workshop_id),
                )
            if labour_rate_cents is not None:
                self._conn.execute(
                    "UPDATE workshops SET labour_rate_cents = ? WHERE id = ?",
                    (int(labour_rate_cents), workshop_id),
                )

    def list_workshops(self):
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT w.*,
                    (SELECT COUNT(*) FROM vehicles v
                     WHERE v.workshop_id = w.id) AS vehicle_count,
                    (SELECT COUNT(*) FROM vehicles v
                     WHERE v.workshop_id = w.id AND v.status = 'open')
                        AS open_count,
                    (SELECT COUNT(*) FROM users u
                     WHERE u.workshop_id = w.id) AS user_count
                FROM workshops w ORDER BY w.name COLLATE NOCASE
                """
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_workshop(self, workshop_id):
        with self._lock, self._conn:
            self._conn.execute(
                "DELETE FROM workshops WHERE id = ?", (workshop_id,)
            )

    # ---------------------------------------------------------- vehicles

    def list_vehicles(self, workshop_id=None, scope="open", query=""):
        sql = """
            SELECT v.*, w.name AS workshop_name, w.labour_rate_cents,
                (SELECT COUNT(*) FROM repair_items i
                 WHERE i.vehicle_id = v.id) AS item_count,
                (SELECT COUNT(*) FROM repair_items i
                 WHERE i.vehicle_id = v.id AND i.done = 1) AS item_done_count,
                (SELECT COUNT(*) FROM parts p
                 WHERE p.vehicle_id = v.id) AS part_count
            FROM vehicles v JOIN workshops w ON w.id = v.workshop_id
            WHERE 1 = 1
        """
        args = []
        if workshop_id is not None:
            sql += " AND v.workshop_id = ?"
            args.append(workshop_id)
        if scope == "open":
            sql += " AND v.status = 'open'"
        if query:
            sql += (
                " AND (v.registration LIKE ? OR v.customer LIKE ?"
                " OR v.job LIKE ?)"
            )
            like = "%" + query + "%"
            args.extend([like, like, like])
        sql += " ORDER BY v.created_at DESC"
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        vehicles = [dict(r) for r in rows]
        for vehicle in vehicles:
            vehicle["parts"] = self._parts_for(vehicle["id"])
        return vehicles

    def _parts_for(self, vehicle_id):
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM parts WHERE vehicle_id = ? ORDER BY id",
                (vehicle_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def _items_for(self, vehicle_id):
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM repair_items WHERE vehicle_id = ?"
                " ORDER BY position, id",
                (vehicle_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def create_vehicle(self, workshop_id, fields, item_texts):
        with self._lock, self._conn:
            cur = self._conn.execute(
                """
                INSERT INTO vehicles (workshop_id, registration, year, make,
                    customer, phone, job, labour_hours, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workshop_id,
                    fields.get("registration", ""),
                    fields.get("year"),
                    fields.get("make", ""),
                    fields.get("customer", ""),
                    fields.get("phone", ""),
                    "",
                    float(fields.get("labour_hours") or 0),
                    time.time(),
                ),
            )
            vehicle_id = cur.lastrowid
            for position, text in enumerate(item_texts):
                self._conn.execute(
                    "INSERT INTO repair_items"
                    " (vehicle_id, description, position) VALUES (?, ?, ?)",
                    (vehicle_id, text, position),
                )
            self._sync_job_summary_locked(vehicle_id)
        return vehicle_id

    def get_vehicle(self, vehicle_id):
        with self._lock:
            row = self._conn.execute(
                """
                SELECT v.*, w.name AS workshop_name, w.labour_rate_cents
                FROM vehicles v JOIN workshops w ON w.id = v.workshop_id
                WHERE v.id = ?
                """,
                (vehicle_id,),
            ).fetchone()
        if not row:
            return None
        vehicle = dict(row)
        vehicle["items"] = self._items_for(vehicle_id)
        vehicle["parts"] = self._parts_for(vehicle_id)
        return vehicle

    def update_vehicle(self, vehicle_id, fields):
        allowed = (
            "registration",
            "year",
            "make",
            "customer",
            "phone",
            "labour_hours",
            "status",
        )
        updates = {k: fields[k] for k in allowed if k in fields}
        if not updates:
            return
        assignments = ", ".join(f"{k} = ?" for k in updates)
        with self._lock, self._conn:
            self._conn.execute(
                f"UPDATE vehicles SET {assignments} WHERE id = ?",
                list(updates.values()) + [vehicle_id],
            )

    def delete_vehicle(self, vehicle_id):
        with self._lock, self._conn:
            self._conn.execute(
                "DELETE FROM vehicles WHERE id = ?", (vehicle_id,)
            )

    # ------------------------------------------------------ repair items

    def add_items(self, vehicle_id, texts):
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT COALESCE(MAX(position), -1) AS p FROM repair_items"
                " WHERE vehicle_id = ?",
                (vehicle_id,),
            ).fetchone()
            position = row["p"] + 1
            for text in texts:
                self._conn.execute(
                    "INSERT INTO repair_items"
                    " (vehicle_id, description, position) VALUES (?, ?, ?)",
                    (vehicle_id, text, position),
                )
                position += 1
            self._sync_job_summary_locked(vehicle_id)

    def get_item(self, item_id):
        with self._lock:
            row = self._conn.execute(
                """
                SELECT i.*, v.workshop_id FROM repair_items i
                JOIN vehicles v ON v.id = i.vehicle_id WHERE i.id = ?
                """,
                (item_id,),
            ).fetchone()
        return dict(row) if row else None

    def set_item_done(self, item_id, done):
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE repair_items SET done = ? WHERE id = ?",
                (1 if done else 0, item_id),
            )

    def delete_item(self, item_id):
        item = self.get_item(item_id)
        if not item:
            return
        with self._lock, self._conn:
            self._conn.execute(
                "DELETE FROM repair_items WHERE id = ?", (item_id,)
            )
            self._sync_job_summary_locked(item["vehicle_id"])

    def _sync_job_summary_locked(self, vehicle_id):
        """Mirror the item list into vehicles.job so free-text search over
        the job summary keeps working.  Caller must hold the lock inside a
        transaction."""
        rows = self._conn.execute(
            "SELECT description FROM repair_items WHERE vehicle_id = ?"
            " ORDER BY position, id",
            (vehicle_id,),
        ).fetchall()
        summary = ", ".join(r["description"] for r in rows)
        self._conn.execute(
            "UPDATE vehicles SET job = ? WHERE id = ?", (summary, vehicle_id)
        )

    # --------------------------------------------------------------- parts

    def add_part(self, vehicle_id, fields):
        with self._lock, self._conn:
            cur = self._conn.execute(
                """
                INSERT INTO parts (vehicle_id, part_number, name, supplier,
                    cost_cents, discount_pct, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    vehicle_id,
                    fields.get("part_number", ""),
                    fields.get("name", ""),
                    fields.get("supplier", ""),
                    int(fields.get("cost_cents") or 0),
                    float(fields.get("discount_pct") or 0),
                    fields.get("status", "Ordered"),
                    time.time(),
                ),
            )
        return cur.lastrowid

    def get_part(self, part_id):
        with self._lock:
            row = self._conn.execute(
                """
                SELECT p.*, v.workshop_id FROM parts p
                JOIN vehicles v ON v.id = p.vehicle_id WHERE p.id = ?
                """,
                (part_id,),
            ).fetchone()
        return dict(row) if row else None

    def update_part(self, part_id, fields):
        allowed = (
            "part_number",
            "name",
            "supplier",
            "cost_cents",
            "discount_pct",
            "status",
        )
        updates = {k: fields[k] for k in allowed if k in fields}
        if not updates:
            return
        assignments = ", ".join(f"{k} = ?" for k in updates)
        with self._lock, self._conn:
            self._conn.execute(
                f"UPDATE parts SET {assignments} WHERE id = ?",
                list(updates.values()) + [part_id],
            )

    def delete_part(self, part_id):
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM parts WHERE id = ?", (part_id,))
