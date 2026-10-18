"""Local, license-free persistence core for the reconstructed desktop UI.

This module intentionally has no recruitment-site automation, browser session,
network call, or activation API. Those capabilities need separately verified
adapters. The methods here match the recovered pywebview UI's local data calls.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import zipfile
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Mapping
from xml.etree import ElementTree

from application_filters import applied_company_reason, company_key
from salary_codec import readable_salary


TASK_FIELDS = (
    "keyword", "city", "search_prompt", "job_prompt", "search_re",
    "job_re", "resume", "match_degree", "platform", "employment_type", "recruitment_track",
)
APPLY_FIELDS = (
    "create_time", "source", "task_id", "match_degree", "submit", "title", "company",
    "area", "salary", "experience", "education", "submit_time", "remarks", "link",
    "search_city", "application_day", "attempt_state", "employment_type", "recruitment_track",
)
CHINA_TIME = timezone(timedelta(hours=8))


def china_day() -> str:
    return datetime.now(CHINA_TIME).date().isoformat()
CHAT_FIELDS = (
    "create_time", "source", "title", "company", "hr_name", "option",
    "msg_reply", "remarks",
)
PLATFORM_GROUPS = frozenset({
    "boss", "qiancheng", "liepin", "guopin", "lagou", "yjs", "gdzhzp",
    "zhilian", "niuke", "jobonline", "jobmdcn", "offertoday", "jobsdbhk",
})
DEFAULT_CONFIG: dict[str, dict[str, Any]] = {
    "apply": {
        "work_mode": "apply_mode",
        "intelligent_perception": "on",
        "company_filter": "不过滤",
        "off_site_filter": "过滤",
        "exclude_sales_roles": False,
        "max_page": None,
        "timing": {"enable": False, "hour": 9, "minute": 0},
        "chat_resume": "", "chat_prompt": "",
    },
    "app": {
        "browser_type": "微软Edge浏览器 Microsoft Edge", "browser_boot": "不隐藏",
        "disable_image": "不禁止", "browser_path": "",
        "bit": {"port": ""}, "miao": "",
    },
    "curr": {
        "apply_scope": "当前", "task_scope": "当前",
        "bit": {"window_id": ""},
    },
}


def synchronized(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapped


class LocalStore:
    """SQLite-backed local data API. Instantiate once per desktop process."""

    def __init__(
        self,
        db_path: str | Path,
        *,
        file_picker: Callable[[list[str]], str | Path | None] | None = None,
        config_dir: str | Path | None = None,
    ) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self._db_path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA busy_timeout=5000")
        self._file_picker = file_picker
        self._config_dir = Path(config_dir) if config_dir else Path(__file__).resolve().parent / "config"
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS task (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                position INTEGER NOT NULL,
                data TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS blocklist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS record (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL CHECK(kind IN ('apply','chat')),
                data TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS config (
                scope TEXT PRIMARY KEY,
                data TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS platform_setting (
                platform TEXT PRIMARY KEY,
                data TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS application_slot (
                day TEXT NOT NULL,
                link TEXT NOT NULL,
                platform TEXT NOT NULL DEFAULT 'BOSS直聘',
                city TEXT NOT NULL,
                company_key TEXT NOT NULL DEFAULT '',
                state TEXT NOT NULL CHECK(state IN ('reserved','confirmed','unknown','released')),
                created_at TEXT NOT NULL,
                PRIMARY KEY(day, platform, link)
            );
        """)
        columns = {row["name"] for row in self._db.execute("PRAGMA table_info(application_slot)")}
        if "platform" not in columns:
            self._db.execute("ALTER TABLE application_slot ADD COLUMN platform TEXT NOT NULL DEFAULT 'BOSS直聘'")
        primary_key = tuple(row["name"] for row in sorted(
            self._db.execute("PRAGMA table_info(application_slot)"), key=lambda row: row["pk"])
            if row["pk"])
        if primary_key != ("day", "platform", "link"):
            # Preserve previous release data while allowing the same job URL to
            # be counted independently for two recruitment-site accounts.
            self._db.executescript("""
                BEGIN IMMEDIATE;
                CREATE TABLE application_slot_next (
                    day TEXT NOT NULL,
                    platform TEXT NOT NULL DEFAULT 'BOSS直聘',
                    link TEXT NOT NULL,
                    city TEXT NOT NULL,
                    company_key TEXT NOT NULL DEFAULT '',
                    state TEXT NOT NULL CHECK(state IN ('reserved','confirmed','unknown','released')),
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(day, platform, link)
                );
                INSERT INTO application_slot_next(day,platform,link,city,state,created_at)
                SELECT day,platform,link,city,state,created_at FROM application_slot;
                DROP TABLE application_slot;
                ALTER TABLE application_slot_next RENAME TO application_slot;
                COMMIT;
            """)
        elif "company_key" not in columns:
            self._db.execute("ALTER TABLE application_slot ADD COLUMN company_key TEXT NOT NULL DEFAULT ''")
        self._db.commit()

    def _sync_confirmed_slots(self) -> None:
        """Count confirmed applications saved by older versions without a slot ledger."""
        rows = self._db.execute("SELECT data FROM record WHERE kind='apply'").fetchall()
        for row in rows:
            item = json.loads(row["data"])
            if item.get("source") != "BOSS直聘" or item.get("submit") != "是":
                continue
            stamp = str(item.get("submit_time") or item.get("create_time") or "")
            day = str(item.get("application_day") or stamp[:10])
            link = str(item.get("link") or "")
            if not link or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
                continue
            self._db.execute(
                "INSERT INTO application_slot(day,link,city,state,created_at,company_key) "
                "VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(day,platform,link) DO UPDATE SET "
                "city=CASE WHEN application_slot.city='' THEN excluded.city ELSE application_slot.city END, "
                "company_key=CASE WHEN application_slot.company_key='' THEN excluded.company_key "
                "ELSE application_slot.company_key END",
                (day, link, str(item.get("search_city") or ""), "confirmed", stamp,
                 company_key(item.get("company"))),
            )

    @synchronized
    def daily_application_usage(self, day: str | None = None,
                                platform: str = "BOSS直聘") -> dict[str, Any]:
        day = day or china_day()
        with self._db:
            self._sync_confirmed_slots()
        rows = self._db.execute(
            "SELECT city,COUNT(*) AS amount FROM application_slot "
            "WHERE day=? AND platform=? AND state!='released' GROUP BY city", (day, platform),
        ).fetchall()
        by_city = {row["city"]: int(row["amount"]) for row in rows}
        return {"day": day, "total": sum(by_city.values()), "by_city": by_city}

    @synchronized
    def reserve_application_slot(self, link: str, city: str, *, day: str | None = None,
                                 daily_limit: int = 120, city_limit: int | None = None,
                                 platform: str = "BOSS直聘", company: str = "",
                                 company_filter: str = "不过滤") -> str:
        """Reserve before clicking. An interrupted process leaves a counted slot."""
        day = day or china_day()
        self._db.execute("BEGIN IMMEDIATE")
        try:
            self._sync_confirmed_slots()
            previous = self._db.execute(
                "SELECT state FROM application_slot WHERE day=? AND link=? AND platform=?",
                (day, link, platform)
            ).fetchone()
            if previous and previous["state"] != "released":
                outcome = "duplicate"
            elif company and company_filter in {
                    "过滤10天内同一平台投递过的公司", "过滤10天内不同平台投递过的公司"} and self._company_slot_conflict(
                        company, company_filter, platform, day):
                outcome = "company_limit"
            elif self._db.execute(
                "SELECT COUNT(*) FROM application_slot WHERE day=? AND platform=? AND state!='released'",
                (day, platform)
            ).fetchone()[0] >= daily_limit:
                outcome = "daily_limit"
            elif city_limit is not None and self._db.execute(
                "SELECT COUNT(*) FROM application_slot "
                "WHERE day=? AND platform=? AND city=? AND state!='released'",
                (day, platform, city)
            ).fetchone()[0] >= city_limit:
                outcome = "city_limit"
            else:
                self._db.execute(
                    "INSERT INTO application_slot(day,link,city,state,created_at,platform,company_key) "
                    "VALUES(?,?,?,?,?,?,?) "
                    "ON CONFLICT(day,platform,link) DO UPDATE SET city=excluded.city, "
                    "state='reserved',created_at=excluded.created_at",
                    (day, link, city, "reserved", datetime.now(CHINA_TIME).isoformat(timespec="seconds"),
                     platform, company_key(company)),
                )
                outcome = "reserved"
            self._db.commit()
            return outcome
        except Exception:
            self._db.rollback()
            raise

    def _company_slot_conflict(self, company: str, mode: str,
                               platform: str, day: str) -> bool:
        first_day = (datetime.fromisoformat(day).date() - timedelta(days=9)).isoformat()
        params: tuple[Any, ...] = (first_day, day, company_key(company))
        same_platform = mode == "过滤10天内同一平台投递过的公司"
        if same_platform:
            params += (platform,)
        query = ("SELECT 1 FROM application_slot WHERE day BETWEEN ? AND ? "
                 "AND company_key=? AND state!='released'" +
                 (" AND platform=?" if same_platform else "") + " LIMIT 1")
        if self._db.execute(query, params).fetchone():
            return True
        rows = (json.loads(row["data"]) for row in self._db.execute(
            "SELECT data FROM record WHERE kind='apply'"))
        return applied_company_reason(company, rows, mode, platform, day) is not None

    @synchronized
    def finalize_application_slot(self, link: str, state: str, *, day: str | None = None,
                                  platform: str = "BOSS直聘") -> None:
        if state not in {"confirmed", "unknown", "released"}:
            raise ValueError("Invalid application slot state")
        allowed = "('reserved','unknown')" if state == "confirmed" else "('reserved')"
        with self._db:
            self._db.execute(
                "UPDATE application_slot SET state=? WHERE day=? AND link=? AND platform=? AND state IN " + allowed,
                (state, day or china_day(), link, platform),
            )

    @synchronized
    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> "LocalStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def database_path(self) -> Path:
        """Return the SQLite path without exposing a nested Path to pywebview."""
        return self._db_path

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _id(value: Any) -> int:
        try:
            number = int(value)
        except (ValueError, TypeError) as exc:
            raise ValueError("ID must be an integer") from exc
        if number <= 0:
            raise ValueError("ID must be positive")
        return number

    @staticmethod
    def _task_data(task: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(task, Mapping):
            raise TypeError("task must be a mapping")
        result = {name: task.get(name, "") for name in TASK_FIELDS}
        result["keyword"] = str(result["keyword"] or "").strip()
        result["city"] = str(result["city"] or "").strip()
        if not result["keyword"] or not result["city"]:
            raise ValueError("keyword and city are required")
        for name in ("search_prompt", "job_prompt", "search_re", "job_re", "resume"):
            result[name] = str(result[name] or "")
        for name in ("search_re", "job_re"):
            if result[name]:
                re.compile(result[name])
        try:
            degree = int(result["match_degree"])
        except (ValueError, TypeError) as exc:
            raise ValueError("match_degree must be an integer") from exc
        if not 0 <= degree <= 95:
            raise ValueError("match_degree must be 0..95")
        result["match_degree"] = degree
        platforms = result["platform"]
        if isinstance(platforms, (list, tuple)):
            platforms = ",".join(str(x) for x in platforms)
        result["platform"] = str(platforms).strip() if platforms is not None else None
        result["employment_type"] = str(result["employment_type"] or "full_time")
        if result["employment_type"] not in {"full_time", "internship"}:
            raise ValueError("employment_type must be full_time or internship")
        result["recruitment_track"] = str(result["recruitment_track"] or "all")
        if result["recruitment_track"] not in {"all", "campus", "social"}:
            raise ValueError("recruitment_track must be all, campus or social")
        return result

    @synchronized
    def get_tasks(self) -> list[dict[str, Any]]:
        rows = self._db.execute("SELECT id,data FROM task ORDER BY position,id").fetchall()
        return [{"id": row["id"], **json.loads(row["data"])} for row in rows]

    @synchronized
    def get_task(self, platform: str) -> dict[str, Any] | None:
        for task in self.get_tasks():
            selected = task["platform"]
            if selected is None or platform in selected.split(","):
                return task
        return None

    @synchronized
    def save_task(self, task: Mapping[str, Any]) -> int:
        data = self._task_data(task)
        next_pos = self._db.execute("SELECT COALESCE(MAX(position),0)+1 FROM task").fetchone()[0]
        with self._db:
            cursor = self._db.execute(
                "INSERT INTO task(position,data) VALUES(?,?)", (next_pos, self._json(data))
            )
        return int(cursor.lastrowid)

    @synchronized
    def update_task(self, task: Mapping[str, Any]) -> bool:
        task_id = self._id(task.get("id"))
        data = self._task_data(task)
        with self._db:
            cursor = self._db.execute(
                "UPDATE task SET data=? WHERE id=?", (self._json(data), task_id)
            )
        return cursor.rowcount > 0

    @synchronized
    def alter_task(self, action: str, data: Any) -> bool:
        if action == "delete":
            with self._db:
                cursor = self._db.execute("DELETE FROM task WHERE id=?", (self._id(data),))
            return cursor.rowcount > 0
        if action not in {"move_up", "move_down"} or not isinstance(data, Mapping):
            raise ValueError("Unsupported task action")
        neighbor_key = "prev" if action == "move_up" else "next"
        current_id, neighbor_id = self._id(data.get("curr")), self._id(data.get(neighbor_key))
        rows = self._db.execute(
            "SELECT id,position FROM task WHERE id IN (?,?)", (current_id, neighbor_id)
        ).fetchall()
        if len(rows) != 2:
            return False
        positions = {row["id"]: row["position"] for row in rows}
        ordered = [row["id"] for row in self._db.execute("SELECT id FROM task ORDER BY position,id")]
        curr_idx = ordered.index(current_id)
        expected_idx = curr_idx - 1 if action == "move_up" else curr_idx + 1
        if not (0 <= expected_idx < len(ordered)) or ordered[expected_idx] != neighbor_id:
            return False
        # Temporary position avoids a uniqueness dependency and keeps IDs stable.
        with self._db:
            self._db.execute("UPDATE task SET position=? WHERE id=?", (positions[neighbor_id], current_id))
            self._db.execute("UPDATE task SET position=? WHERE id=?", (positions[current_id], neighbor_id))
        return True

    @synchronized
    def get_blocklist(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._db.execute("SELECT id,company FROM blocklist ORDER BY id")]

    @synchronized
    def save_blocklist(self, item: Mapping[str, Any]) -> int:
        company = str(item.get("company", "")).strip()
        if not company:
            raise ValueError("company is required")
        if len(company) > 120:
            raise ValueError("公司黑名单表达式不能超过 120 个字符")
        try:
            re.compile(company, re.I)
        except re.error as exc:
            raise ValueError(f"公司黑名单正则表达式无效：{exc}") from exc
        with self._db:
            cursor = self._db.execute("INSERT INTO blocklist(company) VALUES(?)", (company,))
        return int(cursor.lastrowid)

    @synchronized
    def alter_blocklist(self, action: str, item_id: Any) -> bool:
        if action != "delete":
            raise ValueError("Unsupported blocklist action")
        with self._db:
            cursor = self._db.execute("DELETE FROM blocklist WHERE id=?", (self._id(item_id),))
        return cursor.rowcount > 0

    def _get_config(self, scope: str) -> dict[str, Any]:
        row = self._db.execute("SELECT data FROM config WHERE scope=?", (scope,)).fetchone()
        return json.loads(row["data"]) if row else deepcopy(DEFAULT_CONFIG[scope])

    def _set_config(self, scope: str, key: str, value: Any) -> bool:
        parts = key.split(".")
        if not parts or any(not part or part == "__proto__" for part in parts):
            raise ValueError("Invalid configuration path")
        obj = self._get_config(scope)
        target = obj
        for part in parts[:-1]:
            existing = target.get(part)
            if existing is None:
                target[part] = {}
            elif not isinstance(existing, dict):
                raise ValueError("Configuration path crosses a scalar")
            target = target[part]
        target[parts[-1]] = value
        with self._db:
            self._db.execute(
                "INSERT INTO config(scope,data) VALUES(?,?) "
                "ON CONFLICT(scope) DO UPDATE SET data=excluded.data",
                (scope, self._json(obj)),
            )
        return True

    @staticmethod
    def _dot_get(obj: Mapping[str, Any], key: str | None) -> Any:
        if key is None:
            return dict(obj)
        value: Any = obj
        for part in key.split("."):
            if not isinstance(value, Mapping):
                return None
            value = value.get(part)
        return value

    @synchronized
    def get_apply_config(self, key: str | None = None) -> Any:
        return self._dot_get(self._get_config("apply"), key)

    @synchronized
    def set_apply_config(self, key: str, value: Any) -> bool:
        return self._set_config("apply", key, value)

    @synchronized
    def get_app_config(self, key: str | None = None) -> Any:
        return self._dot_get(self._get_config("app"), key)

    @synchronized
    def set_app_config(self, key: str, value: Any) -> bool:
        return self._set_config("app", key, value)

    @synchronized
    def get_curr_config(self, key: str | None = None) -> Any:
        return self._dot_get(self._get_config("curr"), key)

    @synchronized
    def set_curr_config(self, key: str, value: Any) -> bool:
        return self._set_config("curr", key, value)

    @synchronized
    def get_platform_setting(self, platform: str) -> dict[str, Any]:
        if platform not in PLATFORM_GROUPS:
            raise ValueError("Unknown platform setting group")
        row = self._db.execute(
            "SELECT data FROM platform_setting WHERE platform=?", (platform,)
        ).fetchone()
        if row:
            return json.loads(row["data"])
        bundled = self._config_dir / platform / "filter.json"
        return json.loads(bundled.read_text(encoding="utf-8")) if bundled.is_file() else {}

    @synchronized
    def set_platform_setting(self, platform: str, options: Mapping[str, Any]) -> bool:
        if platform not in PLATFORM_GROUPS or not isinstance(options, Mapping):
            raise ValueError("Invalid platform setting")
        for key, definition in options.items():
            if not isinstance(key, str) or not isinstance(definition, Mapping):
                raise ValueError("Invalid filter definition")
            if definition.get("selectionMode") not in {"single", "multiple", "hidden"}:
                raise ValueError("Unknown selection mode")
            if not isinstance(definition.get("options"), list):
                raise ValueError("Filter options must be a list")
            for option in definition["options"]:
                if not isinstance(option, Mapping) or not {"code", "name"} <= option.keys():
                    raise ValueError("Each option needs code and name")
        with self._db:
            self._db.execute(
                "INSERT INTO platform_setting(platform,data) VALUES(?,?) "
                "ON CONFLICT(platform) DO UPDATE SET data=excluded.data",
                (platform, self._json(dict(options))),
            )
        return True

    def _add_record(self, kind: str, item: Mapping[str, Any]) -> int:
        if not isinstance(item, Mapping):
            raise TypeError("record must be a mapping")
        fields = APPLY_FIELDS if kind == "apply" else CHAT_FIELDS
        record = {field: item.get(field, "") for field in fields}
        record["create_time"] = record["create_time"] or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._db:
            cursor = self._db.execute(
                "INSERT INTO record(kind,data) VALUES(?,?)", (kind, self._json(record))
            )
        return int(cursor.lastrowid)

    @synchronized
    def add_apply_record(self, item: Mapping[str, Any]) -> int:
        return self._add_record("apply", item)

    @synchronized
    def update_apply_record(self, record_id: Any, item: Mapping[str, Any]) -> bool:
        row = self._db.execute(
            "SELECT data FROM record WHERE id=? AND kind='apply'", (self._id(record_id),)
        ).fetchone()
        if row is None:
            return False
        data = json.loads(row["data"])
        data.update({key: item[key] for key in APPLY_FIELDS if key in item})
        with self._db:
            self._db.execute("UPDATE record SET data=? WHERE id=? AND kind='apply'",
                             (self._json(data), self._id(record_id)))
        return True

    @synchronized
    def add_chat_record(self, item: Mapping[str, Any]) -> int:
        return self._add_record("chat", item)

    def _get_records(self, kind: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT id,data FROM record WHERE kind=? ORDER BY id DESC", (kind,)
        ).fetchall()
        return [{"id": row["id"], **json.loads(row["data"])} for row in rows]

    @synchronized
    def get_apply_record(self) -> list[dict[str, Any]]:
        rows = self._get_records("apply")
        for row in rows:
            row["salary"] = readable_salary(row.get("salary", ""))
        return rows

    @synchronized
    def get_chat_record(self) -> list[dict[str, Any]]:
        return self._get_records("chat")

    @staticmethod
    def keywords_to_regex(include: str, exclude: str, mode: str = "OR") -> str:
        """Build a JS-compatible regular expression; no hidden matching semantics."""
        if mode not in {"OR", "AND"}:
            raise ValueError("mode must be OR or AND")
        include_terms = [re.escape(s) for s in include.split() if s]
        exclude_terms = [re.escape(s) for s in exclude.split() if s]
        positive = (
            "".join(r"(?=[\s\S]*" + term + ")" for term in include_terms)
            if mode == "AND" else
            (r"(?=[\s\S]*(?:" + "|".join(include_terms) + "))" if include_terms else "")
        )
        negative = (
            r"(?![\s\S]*(?:" + "|".join(exclude_terms) + "))"
            if exclude_terms else ""
        )
        return "^" + positive + negative + r"[\s\S]*$"

    @staticmethod
    def regex_to_keywords(pattern: str) -> list[str]:
        """Reverse only simple patterns generated above; arbitrary regex stays opaque."""
        if not pattern.startswith("^") or not pattern.endswith(r"[\s\S]*$"):
            return ["", ""]
        body = pattern[1:-8]
        pos_or = re.search(r"\(\?=\[\\s\\S\]\*\(\?:(.*?)\)\)", body)
        neg = re.search(r"\(\?!\[\\s\\S\]\*\(\?:(.*?)\)\)", body)
        if pos_or:
            included = pos_or.group(1).split("|")
        else:
            included = re.findall(r"\(\?=\[\\s\\S\]\*(.*?)\)", body)
        excluded = neg.group(1).split("|") if neg else []
        unescape = lambda terms: " ".join(re.sub(r"\\(.)", r"\1", term) for term in terms)
        return [unescape(included), unescape(excluded)]

    def get_file_content(self, file_types: list[str] | str | Path | None = None) -> str:
        """Read explicit path, or ask an injected desktop file picker for one."""
        if isinstance(file_types, (str, Path)):
            selected = file_types
        elif self._file_picker:
            selected = self._file_picker(file_types or ["简历 (*.docx;*.pdf)"])
        else:
            raise RuntimeError("A desktop file picker must be injected")
        return self.extract_resume_text(selected) if selected else ""

    @staticmethod
    def extract_resume_text(path: str | Path) -> str:
        path = Path(path)
        if path.suffix.lower() == ".docx":
            with zipfile.ZipFile(path) as archive:
                root = ElementTree.fromstring(archive.read("word/document.xml"))
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            paragraphs = []
            for paragraph in root.findall(".//w:p", ns):
                text = "".join(node.text or "" for node in paragraph.findall(".//w:t", ns))
                if text.strip():
                    paragraphs.append(text)
            return "\n".join(paragraphs)
        if path.suffix.lower() == ".pdf":
            try:
                from pypdf import PdfReader
            except ImportError as exc:
                raise RuntimeError("PDF extraction requires pypdf") from exc
            return "\n".join((page.extract_text() or "") for page in PdfReader(str(path)).pages).strip()
        raise ValueError("Only .docx and .pdf resumes are supported")


LocalBackend = LocalStore
Backend = LocalStore
