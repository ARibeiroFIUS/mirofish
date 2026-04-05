"""
Índice SQLite do histórico de simulações (metadados enriquecidos).

Espelha o resultado de GET /api/simulation/history para consulta offline,
handoff entre agentes e backup versionável (arquivo único).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger("mirofish.history_index_db")

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS simulation_history_index (
    simulation_id TEXT PRIMARY KEY,
    project_id TEXT,
    graph_id TEXT,
    report_id TEXT,
    status TEXT,
    simulation_requirement TEXT,
    created_at TEXT,
    updated_at TEXT,
    current_round INTEGER,
    total_rounds INTEGER,
    payload_json TEXT NOT NULL,
    synced_at TEXT NOT NULL
);
"""


def _db_path() -> str:
    return os.path.abspath(Config.HISTORY_INDEX_DB_PATH)


def _connect() -> sqlite3.Connection:
    path = _db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(_CREATE_SQL)
        conn.commit()


def _safe_ts_for_filename(iso_ts: str) -> str:
    return re.sub(r"[^\dT]", "", iso_ts.replace("+00:00", "Z").split(".")[0])[:17]


def _copy_index_bundle(
    dest_root: str,
    synced_at: str,
    row_count: int,
    with_snapshots: bool,
    log_label: str,
) -> None:
    dest_root = os.path.abspath(os.path.expanduser(dest_root.strip()))
    try:
        os.makedirs(dest_root, exist_ok=True)
        src = _db_path()
        if not os.path.isfile(src):
            return
        latest = os.path.join(dest_root, "mirofish_history.sqlite")
        shutil.copy2(src, latest)
        manifest = {
            "synced_at": synced_at,
            "simulation_rows": row_count,
            "sqlite_source": src,
            "sqlite_copied_to": latest,
            "backup_label": log_label,
        }
        with open(
            os.path.join(dest_root, "mirofish_history_manifest.json"),
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        if with_snapshots:
            snap_dir = os.path.join(dest_root, "snapshots")
            os.makedirs(snap_dir, exist_ok=True)
            suffix = _safe_ts_for_filename(synced_at)
            snap = os.path.join(snap_dir, f"mirofish_history_{suffix}.sqlite")
            shutil.copy2(src, snap)
        logger.info("history_index_db: cópia (%s) em %s", log_label, dest_root)
    except Exception as e:
        logger.warning("history_index_db: cópia (%s) falhou: %s", log_label, e)


def _mirror_all_backup_destinations(synced_at: str, row_count: int) -> None:
    if not getattr(Config, "MIROFISH_DISABLE_PROJECT_BACKUP", False):
        _copy_index_bundle(
            Config.MIROFISH_PROJECT_BACKUP_DIR,
            synced_at,
            row_count,
            getattr(Config, "MIROFISH_PROJECT_BACKUP_VERSIONED", False),
            "projeto",
        )
    ext = (getattr(Config, "MIROFISH_EXTERNAL_BACKUP_DIR", None) or "").strip()
    if ext:
        _copy_index_bundle(
            ext,
            synced_at,
            row_count,
            getattr(Config, "MIROFISH_EXTERNAL_BACKUP_VERSIONED", False),
            "externo",
        )


def replace_all_from_enriched(enriched: List[Dict[str, Any]]) -> None:
    """
    Substitui o índice pelo snapshot atual (mesma ordem / conjunto que a API /history).
    Lista vazia limpa a tabela.
    """
    init_db()
    synced_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for item in enriched or []:
        sid = item.get("simulation_id")
        if not sid:
            continue
        payload = json.dumps(item, ensure_ascii=False)
        rows.append(
            (
                sid,
                item.get("project_id") or "",
                item.get("graph_id") or "",
                item.get("report_id") or "",
                item.get("status") or "",
                item.get("simulation_requirement") or "",
                item.get("created_at") or "",
                item.get("updated_at") or "",
                int(item.get("current_round") or 0),
                int(item.get("total_rounds") or 0),
                payload,
                synced_at,
            )
        )
    try:
        with _connect() as conn:
            conn.execute("DELETE FROM simulation_history_index")
            if rows:
                conn.executemany(
                    """
                    INSERT INTO simulation_history_index (
                        simulation_id, project_id, graph_id, report_id, status,
                        simulation_requirement, created_at, updated_at,
                        current_round, total_rounds, payload_json, synced_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
            conn.commit()
        logger.info(
            "history_index_db: %s registros gravados em %s", len(rows), _db_path()
        )
        _mirror_all_backup_destinations(synced_at, len(rows))
    except Exception as e:
        logger.warning("history_index_db: falha ao sincronizar: %s", e)


def fetch_persisted(limit: int = 50) -> List[Dict[str, Any]]:
    """Lê registros do SQLite (payload completo por linha)."""
    init_db()
    limit = max(1, min(int(limit), 500))
    with _connect() as conn:
        cur = conn.execute(
            """
            SELECT payload_json FROM simulation_history_index
            ORDER BY datetime(COALESCE(updated_at, created_at)) DESC
            LIMIT ?
            """,
            (limit,),
        )
        out: List[Dict[str, Any]] = []
        for row in cur.fetchall():
            try:
                out.append(json.loads(row["payload_json"]))
            except json.JSONDecodeError:
                continue
        return out


def get_db_file_path() -> str:
    return _db_path()
