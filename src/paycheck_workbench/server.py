"""HTTP 服务：静态单页 + JSON API（本地单用户，仅绑定 127.0.0.1）

API：
  GET  /                      单页应用（static/index.html）
  GET  /api/meta              各源记录数、库路径、版本
  GET  /api/options?source=   该源的逻辑列 / 筛选选项 / 分页档位（支持 source=total）
  GET  /api/rows?source=...   筛选 + 排序 + 分页查询（source=total 返回三区结构：income/expense/flow）
  GET  /api/summary?source=... 汇总卡片（source=total 返回真实收入/真实支出/内部流动三口径）
  POST /api/import/preview        解析单个文件，返回预览与去重比对（不写入）
  POST /api/import/confirm        解析单个文件并写入（幂等）
  POST /api/import/preview-batch  解析多个文件（multipart），返回逐文件与合并统计（不写入）
  GET  /api/rules             内部转账规则列表（附实时命中笔数）
  POST /api/rules             新建规则 · PUT /api/rules/{id} 改含启停 · DELETE /api/rules/{id}
  POST /api/rules/preview     草稿条件试算命中笔数
  GET  /api/presets           内置预设库（附预计命中笔数）
  POST /api/rules/import      从预设批量创建规则（同名同条件跳过）
"""

from __future__ import annotations

import json
import re
import sqlite3
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import List, Optional, Tuple

from paycheck_workbench import __version__
from paycheck_workbench import db
from paycheck_workbench import rules
from paycheck_workbench import total
from paycheck_workbench.parsing import ParseError, parse_file
from paycheck_workbench.sources import (
    ALLOWED_EXTENSIONS,
    SOURCE_CONFIGS,
    SOURCES,
    TOTAL_COLUMNS,
    TOTAL_DIRECTIONS,
    TOTAL_NEUTRAL,
    TOTAL_SOURCE,
)

_INDEX_HTML = Path(__file__).parent / "static" / "index.html"
MAX_UPLOAD_BYTES = 64 * 1024 * 1024  # 单文件上限 64MB（本地账单规模远小于此）
MAX_BATCH_UPLOAD_BYTES = 256 * 1024 * 1024  # 一次批量上传总上限
MAX_BATCH_FILES = 50  # 一次批量导入的文件数上限


class ApiError(Exception):
    """HTTP 400 级错误"""


def _json(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


def _parse_list(value: Optional[str]) -> Optional[list]:
    if not value:
        return None
    return [item for item in value.split(",") if item]


def _parse_float(value: Optional[str]) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError as exc:
        raise ApiError(f"参数不是有效数字：{value}") from exc


def _parse_int(value: Optional[str], default: int, minimum: int = 1) -> int:
    if value in (None, ""):
        return default
    try:
        return max(int(value), minimum)
    except ValueError as exc:
        raise ApiError(f"参数不是有效整数：{value}") from exc


def _decode_part_filename(raw: str) -> str:
    """解析 multipart 中的文件名：头按 latin-1 读回原始字节，再按 UTF-8 解码（浏览器直发 UTF-8）。"""
    name = raw
    if "%" in name:  # 个别实现会对文件名做百分号编码
        try:
            name = urllib.parse.unquote(name)
        except Exception:
            pass
    try:
        return name.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name


def _parse_multipart_files(body: bytes, content_type: str) -> List[Tuple[str, bytes]]:
    """解析 multipart/form-data 请求体，返回 [(文件名, 内容)]（忽略无 filename 的字段）。"""
    match = re.search(r'boundary="?([^";\s]+)"?', content_type)
    if not match:
        raise ApiError("multipart 请求缺少 boundary")
    delim = b"--" + match.group(1).encode("utf-8")
    files: List[Tuple[str, bytes]] = []
    for section in body.split(delim):
        if not section or section.startswith(b"--") or not section.strip():
            continue  # 前言 / 结束符 / 空段
        if section.startswith(b"\r\n"):
            section = section[2:]
        head, sep, content = section.partition(b"\r\n\r\n")
        if not sep:
            continue
        if content.endswith(b"\r\n"):
            content = content[:-2]
        head_text = head.decode("latin-1")
        name_match = re.search(r'name="?files"?\s*;\s*filename="([^"]*)"', head_text, re.I)
        if not name_match:
            name_match = re.search(r'name="?files"?\s*;\s*filename=([^\s;]+)', head_text, re.I)
        if not name_match:
            continue
        files.append((_decode_part_filename(name_match.group(1)), content))
    return files


def _preview_stats(cfg, parsed, source: str, existing: set, seen: set) -> dict:
    """逐行统计：收支分布、日期范围、新增/重复（库内已有 ∪ 批内已见）/无效键。

    seen 就地累积本文件的新增键；返回 dict 含 row_count / error_count / invalid_count /
    new_count / dup_count / date_min / date_max / distribution。
    """
    col_map = {c: i for i, c in enumerate(parsed.columns)}
    time_idx = col_map[cfg.date_col]
    amount_idx = col_map[cfg.amount_col]
    dir_idx = col_map[cfg.direction_col]

    income = expense = neutral = 0
    income_sum = expense_sum = neutral_sum = 0.0
    date_min = date_max = ""
    for row in parsed.rows:
        values = row.values
        direction = values[dir_idx]
        try:
            amount = float(values[amount_idx]) if values[amount_idx] else 0.0
        except ValueError:
            amount = 0.0
        if direction == "收入":
            income += 1
            income_sum += amount
        elif direction == "支出":
            expense += 1
            expense_sum += amount
        elif cfg.neutral_direction and direction == cfg.neutral_direction:
            neutral += 1
            neutral_sum += amount
        time_value = values[time_idx]
        if time_value:
            if not date_min or time_value < date_min:
                date_min = time_value
            if not date_max or time_value > date_max:
                date_max = time_value

    new_count = dup_count = invalid_count = 0
    for row in parsed.rows:
        key = db.dedup_key(source, dict(zip(parsed.columns, row.values)))
        if not key:
            invalid_count += 1  # 空键行在 confirm 阶段计入失败
        elif key in existing or key in seen:
            dup_count += 1
        else:
            new_count += 1
            seen.add(key)

    dist = [{"label": "收入", "count": income, "sum": round(income_sum, 2)}]
    if cfg.neutral_direction:
        dist.append({"label": "支出", "count": expense, "sum": round(expense_sum, 2)})
        dist.append({"label": cfg.neutral_direction, "count": neutral, "sum": round(neutral_sum, 2)})
    else:
        dist.append({"label": "支出", "count": expense, "sum": round(expense_sum, 2)})

    return {
        "row_count": len(parsed.rows),
        "error_count": len(parsed.errors),
        "invalid_count": invalid_count,
        "new_count": new_count,
        "dup_count": dup_count,
        "date_min": date_min[:10],
        "date_max": date_max[:10],
        "distribution": dist,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = f"PayCheckWorkbench/{__version__}"
    db_path = None  # 由 serve() 注入

    # ---- 基础设施 ----

    def log_message(self, fmt, *args):  # 静默访问日志（本地工具）
        pass

    def _send(self, status: int, payload: dict, content_type: str = "application/json; charset=utf-8"):
        body = _json(payload)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status: int, message: str):
        self._send(status, {"ok": False, "error": message})

    def _connect(self) -> sqlite3.Connection:
        return db.connect(self.db_path)

    def _read_upload(self):
        """原始 body 上传：X-Source / X-Filename 头携带来源与文件名（无 multipart）。"""
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            raise ApiError("请求体为空")
        if length > MAX_UPLOAD_BYTES:
            raise ApiError("文件超过 64MB 上限")
        source = self.headers.get("X-Source", "")
        file_name = urllib.parse.unquote(self.headers.get("X-Filename", ""))
        if source not in SOURCE_CONFIGS:
            raise ApiError(f"未知数据源：{source}")
        if not file_name:
            raise ApiError("缺少文件名")
        return source, file_name, self.rfile.read(length)

    # ---- GET ----

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        try:
            if parsed.path == "/":
                self._serve_index()
            elif parsed.path == "/api/meta":
                self._api_meta()
            elif parsed.path == "/api/options":
                self._api_options(parsed)
            elif parsed.path == "/api/rows":
                self._api_rows(parsed)
            elif parsed.path == "/api/summary":
                self._api_summary(parsed)
            elif parsed.path == "/api/rules":
                self._api_rules()
            elif parsed.path == "/api/presets":
                self._api_presets()
            else:
                self._send_error(404, "Not Found")
        except ApiError as exc:
            self._send_error(400, str(exc))
        except db.DataError as exc:
            self._send_error(400, str(exc))
        except sqlite3.OperationalError as exc:
            self._send_error(500, f"数据库读取失败：{exc}")

    def _serve_index(self):
        try:
            body = _INDEX_HTML.read_bytes()
        except OSError:
            self._send_error(500, "index.html 缺失")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _api_meta(self):
        with self._connect() as conn:
            counts = db.source_counts(conn)
        self._send(200, {
            "ok": True,
            "version": __version__,
            "db_path": str(self.db_path),
            "counts": counts,
            "sources": [
                {"name": s, "label": SOURCE_CONFIGS[s].label} for s in SOURCES
            ],
        })

    def _api_options(self, parsed):
        query = urllib.parse.parse_qs(parsed.query)
        source = (query.get("source") or [""])[0]
        if source == TOTAL_SOURCE:
            self._send(200, {
                "ok": True,
                "source": source,
                "label": "总账户",
                "columns": TOTAL_COLUMNS,
                "directions": TOTAL_DIRECTIONS,
                "neutral": TOTAL_NEUTRAL,
                "category_label": "来源",
                "categories": list(SOURCES),
                "search_placeholder": "搜索对方 / 摘要",
                "date_col": "",
                "time_col": "",
                "direction_col": "direction",
                "amount_col": "amount",
                "balance_col": "",
                "page_sizes": list(db._PAGE_SIZES),
                "default_page_size": db._DEFAULT_PAGE_SIZE,
            })
            return
        cfg = SOURCE_CONFIGS.get(source)
        if not cfg:
            raise ApiError(f"未知数据源：{source}")
        with self._connect() as conn:
            categories = db.distinct_categories(conn, source)
        self._send(200, {
            "ok": True,
            "source": source,
            "label": cfg.label,
            "columns": cfg.logical_columns,
            "directions": cfg.directions,
            "neutral": cfg.neutral_direction,
            "category_label": cfg.category_label,
            "categories": categories,
            "search_placeholder": cfg.search_placeholder,
            "date_col": cfg.date_col,
            "time_col": cfg.time_col,
            "direction_col": cfg.direction_col,
            "amount_col": cfg.amount_col,
            "balance_col": cfg.balance_col,
            "page_sizes": list(db._PAGE_SIZES),
            "default_page_size": db._DEFAULT_PAGE_SIZE,
        })

    def _filter_params(self, query: dict) -> dict:
        get = lambda key: (query.get(key) or [None])[0]  # noqa: E731
        return {
            "q": get("q") or None,
            "date_from": get("date_from") or None,
            "date_to": get("date_to") or None,
            "directions": _parse_list(get("directions")),
            "categories": _parse_list(get("categories")),
            "amount_min": _parse_float(get("amount_min")),
            "amount_max": _parse_float(get("amount_max")),
        }

    def _api_rows(self, parsed):
        query = urllib.parse.parse_qs(parsed.query)
        source = (query.get("source") or [""])[0]
        if source == TOTAL_SOURCE:
            filters = self._filter_params(query)
            filters.pop("categories", None)  # 总账户的「分类」维度是来源多选
            raw_sources = (query.get("sources") or [None])[0]
            sources = _parse_list(raw_sources) if raw_sources else list(SOURCES)
            with self._connect() as conn:
                result = total.query_rows(
                    conn,
                    sort=(query.get("sort") or ["datetime"])[0],
                    order=(query.get("order") or ["desc"])[0],
                    income_page=_parse_int((query.get("income_page") or [None])[0], 1),
                    expense_page=_parse_int((query.get("expense_page") or [None])[0], 1),
                    flow_page=_parse_int((query.get("flow_page") or [None])[0], 1),
                    page_size=_parse_int((query.get("page_size") or [None])[0], db._DEFAULT_PAGE_SIZE),
                    sources=sources,
                    **filters,
                )
            self._send(200, {"ok": True, **result})
            return
        if source not in SOURCE_CONFIGS:
            raise ApiError(f"未知数据源：{source}")
        filters = self._filter_params(query)
        with self._connect() as conn:
            result = db.query_rows(
                conn,
                source,
                page=_parse_int((query.get("page") or [None])[0], 1),
                page_size=_parse_int((query.get("page_size") or [None])[0], db._DEFAULT_PAGE_SIZE),
                sort=(query.get("sort") or ["datetime"])[0],
                order=(query.get("order") or ["desc"])[0],
                **filters,
            )
        self._send(200, {"ok": True, **result})

    def _api_summary(self, parsed):
        query = urllib.parse.parse_qs(parsed.query)
        source = (query.get("source") or [""])[0]
        if source == TOTAL_SOURCE:
            filters = self._filter_params(query)
            filters.pop("categories", None)
            raw_sources = (query.get("sources") or [None])[0]
            sources = _parse_list(raw_sources) if raw_sources else list(SOURCES)
            with self._connect() as conn:
                summary = total.query_summary(conn, sources=sources, **filters)
            self._send(200, {"ok": True, "source": source, **summary})
            return
        if source not in SOURCE_CONFIGS:
            raise ApiError(f"未知数据源：{source}")
        filters = self._filter_params(query)
        with self._connect() as conn:
            summary = db.query_summary(conn, source, **filters)
        self._send(200, {"ok": True, "source": source, **summary})

    # ---- POST ----

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        try:
            if parsed.path == "/api/import/preview":
                self._api_import_preview()
            elif parsed.path == "/api/import/preview-batch":
                self._api_import_preview_batch()
            elif parsed.path == "/api/import/confirm":
                self._api_import_confirm()
            elif parsed.path == "/api/rules":
                self._api_rules_create()
            elif parsed.path == "/api/rules/preview":
                self._api_rules_preview()
            elif parsed.path == "/api/rules/import":
                self._api_rules_import()
            else:
                self._send_error(404, "Not Found")
        except ApiError as exc:
            self._send_error(400, str(exc))
        except db.DataError as exc:
            self._send_error(400, str(exc))
        except sqlite3.OperationalError as exc:
            self._send_error(500, f"数据库写入失败：{exc}")

    # ---- PUT / DELETE ----

    def do_PUT(self):
        parsed = urllib.parse.urlparse(self.path)
        try:
            match = re.fullmatch(r"/api/rules/(\d+)", parsed.path)
            if match:
                self._api_rules_update(int(match.group(1)))
            else:
                self._send_error(404, "Not Found")
        except ApiError as exc:
            self._send_error(400, str(exc))
        except db.DataError as exc:
            self._send_error(400, str(exc))
        except sqlite3.OperationalError as exc:
            self._send_error(500, f"数据库写入失败：{exc}")

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        try:
            match = re.fullmatch(r"/api/rules/(\d+)", parsed.path)
            if match:
                self._api_rules_delete(int(match.group(1)))
            else:
                self._send_error(404, "Not Found")
        except ApiError as exc:
            self._send_error(400, str(exc))
        except db.DataError as exc:
            self._send_error(400, str(exc))
        except sqlite3.OperationalError as exc:
            self._send_error(500, f"数据库写入失败：{exc}")

    def _api_import_preview(self):
        source, file_name, data = self._read_upload()
        try:
            parsed_result = parse_file(source, file_name, data)
        except ParseError as exc:
            self._send(200, {"ok": False, "error": str(exc)})
            return

        cfg = SOURCE_CONFIGS[source]
        with self._connect() as conn:
            existing = db.existing_dedup_keys(conn, source)
        stats = _preview_stats(cfg, parsed_result, source, existing, set())

        self._send(200, {
            "ok": True,
            "source": source,
            "file_name": file_name,
            "columns": parsed_result.columns,
            "row_count": stats["row_count"],
            "error_count": stats["error_count"],
            "date_min": stats["date_min"],
            "date_max": stats["date_max"],
            "distribution": stats["distribution"],
            "new_count": stats["new_count"],
            "dup_count": stats["dup_count"],
            "sample": [r.values for r in parsed_result.rows[:5]],
        })

    def _api_import_preview_batch(self):
        """批量预览：multipart 携带多个文件，返回逐文件统计与合并去重比对（不写入）。"""
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            raise ApiError("请求体为空")
        if length > MAX_BATCH_UPLOAD_BYTES:
            raise ApiError("批量上传总大小超过 256MB 上限")
        source = self.headers.get("X-Source", "")
        if source not in SOURCE_CONFIGS:
            raise ApiError(f"未知数据源：{source}")
        files = _parse_multipart_files(
            self.rfile.read(length), self.headers.get("Content-Type", "")
        )
        if not files:
            raise ApiError("未收到文件")
        if len(files) > MAX_BATCH_FILES:
            raise ApiError(f"一次最多导入 {MAX_BATCH_FILES} 个文件")

        cfg = SOURCE_CONFIGS[source]
        allowed = "、".join(ALLOWED_EXTENSIONS[source])
        with self._connect() as conn:
            existing = db.existing_dedup_keys(conn, source)

        seen: set = set()
        file_stats: List[dict] = []
        columns: List[str] = []
        totals = {"row_count": 0, "new_count": 0, "dup_count": 0, "failed_count": 0, "error_file_count": 0}
        date_min = date_max = ""
        merged_dist: dict = {}
        for file_name, data in files:
            if len(data) > MAX_UPLOAD_BYTES:
                # 与单文件 _read_upload 口径一致：超限文件不解析、不写入
                file_stats.append({"file_name": file_name, "error": "文件超过 64MB 上限"})
                totals["error_file_count"] += 1
                continue
            if Path(file_name).suffix.lower() not in ALLOWED_EXTENSIONS[source]:
                ext = Path(file_name).suffix.lower() or "无扩展名"
                file_stats.append({
                    "file_name": file_name,
                    "error": f"{cfg.label} 只支持 {allowed} 文件（收到 {ext}）",
                })
                totals["error_file_count"] += 1
                continue
            try:
                parsed = parse_file(source, file_name, data)
            except ParseError as exc:
                file_stats.append({"file_name": file_name, "error": str(exc)})
                totals["error_file_count"] += 1
                continue
            stats = _preview_stats(cfg, parsed, source, existing, seen)
            if not columns:
                columns = parsed.columns
            file_stats.append({
                "file_name": file_name,
                "row_count": stats["row_count"],
                "error_count": stats["error_count"],
                "invalid_count": stats["invalid_count"],
                "new_count": stats["new_count"],
                "dup_count": stats["dup_count"],
                "date_min": stats["date_min"],
                "date_max": stats["date_max"],
                "distribution": stats["distribution"],
                "sample": [r.values for r in parsed.rows[:5]],
            })
            totals["row_count"] += stats["row_count"]
            totals["new_count"] += stats["new_count"]
            totals["dup_count"] += stats["dup_count"]
            totals["failed_count"] += stats["error_count"] + stats["invalid_count"]
            # 合并覆盖日期与收支分布（设计 4.2 合并统计次行）
            if stats["date_min"]:
                date_min = stats["date_min"] if not date_min or stats["date_min"] < date_min else date_min
                date_max = stats["date_max"] if not date_max or stats["date_max"] > date_max else date_max
            for item in stats["distribution"]:
                acc = merged_dist.setdefault(item["label"], {"count": 0, "sum": 0.0})
                acc["count"] += item["count"]
                acc["sum"] += item["sum"]

        order = ["收入", "支出"] + ([cfg.neutral_direction] if cfg.neutral_direction else [])
        distribution = [
            {"label": label, "count": merged_dist[label]["count"], "sum": round(merged_dist[label]["sum"], 2)}
            for label in order if label in merged_dist
        ]

        self._send(200, {
            "ok": True,
            "source": source,
            "file_count": len(files),
            "columns": columns,
            "files": file_stats,
            "total_rows": totals["row_count"],
            "total_new": totals["new_count"],
            "total_dup": totals["dup_count"],
            "total_failed": totals["failed_count"],
            "date_min": date_min,
            "date_max": date_max,
            "distribution": distribution,
            "error_file_count": totals["error_file_count"],
        })

    def _api_import_confirm(self):
        source, file_name, data = self._read_upload()
        try:
            parsed_result = parse_file(source, file_name, data)
        except ParseError as exc:
            self._send(200, {"ok": False, "error": str(exc)})
            return
        with self._connect() as conn:
            result = db.import_parse_result(conn, source, parsed_result, file_name)
        self._send(200, {"ok": True, "file_name": file_name, **result})

    # ---- 内部转账规则 API ----

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            raise ApiError("请求体为空")
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ApiError("请求体不是有效 JSON") from exc

    def _validate_rule_body(self, body) -> dict:
        """校验并规整规则请求体；名称留空按条件自动生成。"""
        source = body.get("source") or ""
        conditions = body.get("conditions") or []
        action = body.get("action") or "fold"
        try:
            rules.validate_rule(source, conditions, action)
        except rules.RuleError as exc:
            raise ApiError(str(exc)) from exc
        name = (body.get("name") or "").strip() or rules.auto_name(conditions)
        return {
            "name": name,
            "source": source,
            "conditions": conditions,
            "action": action,
            "enabled": bool(body.get("enabled", True)),
        }

    def _api_rules(self):
        with self._connect() as conn:
            rule_list = db.list_rules(conn)
            for rule in rule_list:
                rule["hit_count"] = db.count_rule_hits(conn, rule)
        self._send(200, {"ok": True, "rules": rule_list})

    def _api_rules_create(self):
        body = self._validate_rule_body(self._read_json())
        with self._connect() as conn:
            saved = db.save_rule(conn, body)
            saved["hit_count"] = db.count_rule_hits(conn, saved)
        self._send(200, {"ok": True, "rule": saved})

    def _api_rules_update(self, rule_id: int):
        body = self._validate_rule_body(self._read_json())
        with self._connect() as conn:
            if db.get_rule(conn, rule_id) is None:
                raise ApiError("规则不存在")
            saved = db.save_rule(conn, body, rule_id=rule_id)
            saved["hit_count"] = db.count_rule_hits(conn, saved)
        self._send(200, {"ok": True, "rule": saved})

    def _api_rules_delete(self, rule_id: int):
        with self._connect() as conn:
            if db.get_rule(conn, rule_id) is None:
                raise ApiError("规则不存在")
            db.delete_rule(conn, rule_id)
        self._send(200, {"ok": True})

    def _api_rules_preview(self):
        body = self._read_json()
        source = body.get("source") or ""
        conditions = body.get("conditions") or []
        try:
            rules.validate_rule(source, conditions, "fold")  # 命中数与处理方式无关
        except rules.RuleError as exc:
            raise ApiError(str(exc)) from exc
        with self._connect() as conn:
            hit_count = db.count_rule_hits(conn, {"source": source, "conditions": conditions})
        self._send(200, {"ok": True, "hit_count": hit_count})

    def _api_presets(self):
        with self._connect() as conn:
            presets = []
            for preset in rules.PRESETS:
                hit_count = None
                if not rules.preset_placeholders(preset):
                    hit_count = sum(db.count_rule_hits(conn, rule) for rule in preset["rules"])
                presets.append({
                    "id": preset["id"],
                    "name": preset["name"],
                    "description": preset["description"],
                    "rules": preset["rules"],
                    "rule_count": len(preset["rules"]),
                    "hit_count": hit_count,
                    "has_placeholder": bool(rules.preset_placeholders(preset)),
                })
        self._send(200, {"ok": True, "presets": presets})

    def _api_rules_import(self):
        body = self._read_json()
        preset_ids = body.get("preset_ids") or []
        replacements = body.get("replacements") or {}
        created: List[dict] = []
        skipped: List[dict] = []
        with self._connect() as conn:
            for preset_id in preset_ids:
                preset = rules.PRESETS_BY_ID.get(preset_id)
                if preset is None:
                    raise ApiError(f"未知预设：{preset_id}")
                try:
                    specs = rules.instantiate_preset(preset, replacements)
                except rules.RuleError as exc:
                    raise ApiError(str(exc)) from exc
                for spec in specs:
                    if db.find_duplicate_rule(conn, spec["name"], spec["conditions"]):
                        skipped.append({
                            "preset_id": preset_id,
                            "preset_name": preset["name"],
                            "name": spec["name"],
                        })
                        continue
                    created.append(db.save_rule(conn, {**spec, "preset_id": preset_id}))
        self._send(200, {"ok": True, "created": created, "skipped": skipped})


def serve(db_path=None, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = False):
    """启动本地服务（阻塞）。db_path 默认当前目录下的 paycheck.db（相对启动目录）。"""
    db_path = Path(db_path) if db_path else db.DEFAULT_DB_PATH
    db.init_db(db_path)

    Handler.db_path = db_path
    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{httpd.server_port}/"
    print(f"账单工作台已启动：{url}")
    print(f"SQLite 数据库：{db_path}")
    if open_browser:
        import webbrowser

        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        httpd.server_close()
