"""HTTP 服务：静态单页 + JSON API（本地单用户，仅绑定 127.0.0.1）

API：
  GET  /                      单页应用（static/index.html）
  GET  /api/meta              各源记录数、库路径、版本
  GET  /api/options?source=   该源的逻辑列 / 筛选选项 / 分页档位
  GET  /api/rows?source=...   筛选 + 排序 + 分页查询
  GET  /api/summary?source=... 汇总卡片（筛选联动）
  POST /api/import/preview    解析文件，返回预览与去重比对（不写入）
  POST /api/import/confirm    解析文件并写入（幂等）
"""

from __future__ import annotations

import json
import sqlite3
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

from paycheck_workbench import __version__
from paycheck_workbench import db
from paycheck_workbench.parsing import ParseError, parse_file
from paycheck_workbench.sources import SOURCE_CONFIGS, SOURCES

_INDEX_HTML = Path(__file__).parent / "static" / "index.html"
MAX_UPLOAD_BYTES = 64 * 1024 * 1024  # 单文件上限 64MB（本地账单规模远小于此）


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
            else:
                self._send_error(404, "Not Found")
        except ApiError as exc:
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
            elif parsed.path == "/api/import/confirm":
                self._api_import_confirm()
            else:
                self._send_error(404, "Not Found")
        except ApiError as exc:
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
        col_map = {c: i for i, c in enumerate(parsed_result.columns)}
        time_idx = col_map[cfg.date_col]
        amount_idx = col_map[cfg.amount_col]
        dir_idx = col_map[cfg.direction_col]

        income = expense = neutral = 0
        income_sum = expense_sum = neutral_sum = 0.0
        date_min = date_max = ""
        for row in parsed_result.rows:
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

        with self._connect() as conn:
            existing = db.existing_dedup_keys(conn, source)
        new_count = dup_count = 0
        seen = set()
        for row in parsed_result.rows:
            key = db.dedup_key(source, dict(zip(parsed_result.columns, row.values)))
            if not key:
                continue  # 空键行在 confirm 阶段计入失败
            if key in existing or key in seen:
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

        self._send(200, {
            "ok": True,
            "source": source,
            "file_name": file_name,
            "columns": parsed_result.columns,
            "row_count": len(parsed_result.rows),
            "error_count": len(parsed_result.errors),
            "date_min": date_min[:10],
            "date_max": date_max[:10],
            "distribution": dist,
            "new_count": new_count,
            "dup_count": dup_count,
            "sample": [r.values for r in parsed_result.rows[:5]],
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
