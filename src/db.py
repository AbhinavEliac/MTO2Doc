"""
SQLite Database Persistence Layer for SID-AI Extraction Threads and Logs.
"""
import os
import json
import sqlite3
from datetime import datetime
from typing import Dict, Any, List, Optional

DB_PATH = os.path.join(os.getcwd(), "extraction_history.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS threads (
                thread_id TEXT PRIMARY KEY,
                filename TEXT,
                drawing_type TEXT DEFAULT 'GENERIC',
                discipline TEXT DEFAULT 'Unknown',
                status TEXT DEFAULT 'QUEUED',
                progress REAL DEFAULT 0.0,
                current_step TEXT DEFAULT 'Initialized',
                created_at TEXT,
                updated_at TEXT,
                duration_sec REAL DEFAULT 0.0,
                error_message TEXT,
                error_traceback TEXT,
                config_json TEXT,
                result_json TEXT
            );
        """)
        try:
            cursor.execute("ALTER TABLE threads ADD COLUMN duration_sec REAL DEFAULT 0.0")
        except Exception:
            pass
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS thread_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id TEXT,
                timestamp TEXT,
                step_name TEXT,
                log_level TEXT DEFAULT 'INFO',
                message TEXT,
                FOREIGN KEY(thread_id) REFERENCES threads(thread_id) ON DELETE CASCADE
            );
        """)
        conn.commit()


def create_thread(
    thread_id: str,
    filename: str,
    config_dict: Dict[str, Any],
    drawing_type: str = "GENERIC",
    discipline: str = "Unknown",
) -> Dict[str, Any]:
    init_db()
    now = datetime.now().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO threads (
                thread_id, filename, drawing_type, discipline, status,
                progress, current_step, created_at, updated_at, config_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                thread_id,
                filename,
                drawing_type,
                discipline,
                "QUEUED",
                0.05,
                "Process Queued",
                now,
                now,
                json.dumps(config_dict),
            ),
        )
        conn.commit()
    add_log(thread_id, "Initialization", f"Extraction thread '{thread_id}' created for file '{filename}'.")
    return get_thread(thread_id)


def update_thread_status(
    thread_id: str,
    status: Optional[str] = None,
    progress: Optional[float] = None,
    current_step: Optional[str] = None,
    error_message: Optional[str] = None,
    error_traceback: Optional[str] = None,
    result_dict: Optional[Dict[str, Any]] = None,
    drawing_type: Optional[str] = None,
    discipline: Optional[str] = None,
    duration_sec: Optional[float] = None,
):
    now = datetime.now().isoformat()
    fields = ["updated_at = ?"]
    params = [now]

    if status is not None:
        fields.append("status = ?")
        params.append(status)
    if progress is not None:
        fields.append("progress = ?")
        params.append(progress)
    if current_step is not None:
        fields.append("current_step = ?")
        params.append(current_step)
    if error_message is not None:
        fields.append("error_message = ?")
        params.append(error_message)
    if error_traceback is not None:
        fields.append("error_traceback = ?")
        params.append(error_traceback)
    if result_dict is not None:
        fields.append("result_json = ?")
        params.append(json.dumps(result_dict, default=str))
    if drawing_type is not None:
        fields.append("drawing_type = ?")
        params.append(drawing_type)
    if discipline is not None:
        fields.append("discipline = ?")
        params.append(discipline)
    if duration_sec is not None:
        fields.append("duration_sec = ?")
        params.append(duration_sec)

    params.append(thread_id)
    sql = f"UPDATE threads SET {', '.join(fields)} WHERE thread_id = ?"

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        conn.commit()


def add_log(thread_id: str, step_name: str, message: str, log_level: str = "INFO"):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO thread_logs (thread_id, timestamp, step_name, log_level, message)
            VALUES (?, ?, ?, ?, ?)
            """,
            (thread_id, now, step_name, log_level, message),
        )
        conn.commit()


def get_all_threads() -> List[Dict[str, Any]]:
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM threads ORDER BY created_at DESC")
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


def get_thread(thread_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM threads WHERE thread_id = ?", (thread_id,))
        row = cursor.fetchone()
        if not row:
            return None
        thread_data = dict(row)

        # Parse JSON fields
        if thread_data.get("config_json"):
            try:
                thread_data["config"] = json.loads(thread_data["config_json"])
            except Exception:
                thread_data["config"] = {}
        if thread_data.get("result_json"):
            try:
                thread_data["result"] = json.loads(thread_data["result_json"])
            except Exception:
                thread_data["result"] = None
        else:
            thread_data["result"] = None

        cursor.execute("SELECT * FROM thread_logs WHERE thread_id = ? ORDER BY id ASC", (thread_id,))
        logs = cursor.fetchall()
        thread_data["logs"] = [dict(l) for l in logs]
        return thread_data


def delete_thread(thread_id: str):
    init_db()
    t = get_thread(thread_id)
    if t and t.get("config"):
        # Cleanup uploaded files if present
        raw_docs = t["config"].get("raw_documents", [])
        for doc in raw_docs:
            if os.path.exists(doc) and "uploads" in doc:
                try:
                    os.remove(doc)
                except Exception:
                    pass

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM thread_logs WHERE thread_id = ?", (thread_id,))
        cursor.execute("DELETE FROM threads WHERE thread_id = ?", (thread_id,))
        conn.commit()
