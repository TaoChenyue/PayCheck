"""HTTP 服务：静态单页 + JSON API（本地单用户，仅绑定 127.0.0.1）

API：
  GET  /                      单页应用（static/index.html）
  GET  /api/meta              各源记录数、库路径、版本、转换目录与 GPU 可用性
  GET  /api/options?source=   该源的逻辑列 / 筛选选项 / 分页档位（支持 source=total）
  GET  /api/rows?source=...   筛选 + 排序 + 分页查询（source=total 为单表口径 + page 分页）
  GET  /api/summary?source=... 汇总卡片（source=total 为计入口径：收入/支出/净收支/计入笔数）
  POST /api/import/preview        解析单个文件，返回预览与去重比对（不写入）
  POST /api/import/confirm        解析单个文件并写入（幂等）
  POST /api/import/preview-batch  解析多个文件（multipart），返回逐文件与合并统计（不写入）
  POST /api/boc/convert           multipart 上传 PDF 列表并启动后台转换任务（运行中 409）
  GET  /api/boc/convert/{job_id}  轮询任务进度（不存在时返回 interrupted）
  POST /api/boc/convert/{job_id}/preview   任务产物 CSV 的解析预览 + 去重比对（不写入）
  POST /api/boc/convert/{job_id}/confirm   任务产物 CSV 写入 SQLite（幂等）
  POST /api/boc/convert/open-dir  调起资源管理器打开转换目录
  PUT  /api/total/overrides   批量设收支属性（ids / filter 两种 scope，方向约束铁律）
  GET  /api/tags              标签组列表（附已打行数）
  POST /api/tags              新建标签组 · PUT /api/tags/{id} 改名 · DELETE /api/tags/{id}
  PUT  /api/tags/apply        批量打/移除标签（ids / filter 两种 scope）
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import List, Optional, Tuple

from paycheck_workbench import __version__
from paycheck_workbench import convert as convert_jobs
from paycheck_workbench import db
from paycheck_workbench import total
from paycheck_workbench.parsing import ParseError, parse_file
from paycheck_workbench.sources import (
    ALLOWED_EXTENSIONS,
    SOURCE_BOC,
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


class ConflictError(ApiError):
    """HTTP 409 级错误（如已有转换任务进行中），可附带 job_id 供前端衔接"""

    def __init__(self, message: str, job_id: Optional[str] = None):
        super().__init__(message)
        self.job_id = job_id


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


def _parse_convert_multipart(body: bytes, content_type: str) -> Tuple[List[Tuple[str, bytes]], dict]:
    """解析 PDF 转换 multipart：返回 ([(文件名, bytes)], {表单字段: 值})。

    files 字段（带 filename）收集为文件，其余字段按 UTF-8 文本收集。
    """
    match = re.search(r'boundary="?([^";\s]+)"?', content_type)
    if not match:
        raise ApiError("multipart 请求缺少 boundary")
    delim = b"--" + match.group(1).encode("utf-8")
    files: List[Tuple[str, bytes]] = []
    form: dict = {}
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
        name_match = re.search(r'name="([^"]*)"', head_text)
        if not name_match:
            continue
        field = name_match.group(1)
        file_match = re.search(r'filename="([^"]*)"', head_text)
        if file_match:
            if field == "files":
                files.append((_decode_part_filename(file_match.group(1)), content))
        else:
            form[field] = content.decode("utf-8", errors="replace").strip()
    return files, form


def _existing_csv_names(convert_dir) -> List[str]:
    """转换目录中已有的 CSV 文件名列表（前端用于「已存在同名 CSV」标注）。"""
    try:
        return sorted(f for f in os.listdir(convert_dir) if f.lower().endswith(".csv"))
    except OSError:
        return []


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


def _batch_preview(cfg, source: str, files: list, existing: set) -> dict:
    """多文件预览（不写入）：逐文件统计 + 合并去重比对，结构与 preview-batch 响应一致。

    files: [(file_name, data, error)]；error 非空时该文件不解析、直接计入错误文件。
    供批量导入预览与 PDF 转换产物预览共用。
    """
    seen: set = set()
    file_stats: List[dict] = []
    columns: List[str] = []
    totals = {"row_count": 0, "new_count": 0, "dup_count": 0, "failed_count": 0, "error_file_count": 0}
    date_min = date_max = ""
    merged_dist: dict = {}
    for file_name, data, error in files:
        if error:
            file_stats.append({"file_name": file_name, "error": error})
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

    return {
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
    }


class Handler(BaseHTTPRequestHandler):
    server_version = f"PayCheckWorkbench/{__version__}"
    db_path = None  # 由 serve() 注入
    convert_dir = None  # 由 serve() 注入（BOC PDF 转换目录）

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
            elif parsed.path == "/api/tags":
                self._api_tags()
            else:
                match = re.fullmatch(r"/api/boc/convert/([0-9a-f]{32})", parsed.path)
                if match:
                    self._api_boc_convert_status(match.group(1))
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
            "convert_dir": str(self.convert_dir),
            # GPU 可用性惰性探测并缓存（首次转换任务时触发），未探测过为 null
            "gpu_available": convert_jobs.gpu_available_cached(),
            "convert_existing_csvs": _existing_csv_names(self.convert_dir),
        })

    def _api_options(self, parsed):
        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
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

    @staticmethod
    def _parse_counted(query: dict) -> Optional[set]:
        """属性筛选参数：缺省 None（不过滤）；「counted=」空值 → 空集合（匹配 0 行）。"""
        if "counted" not in query:
            return None
        raw = query["counted"][0]
        return {v for v in raw.split(",") if v in ("0", "1")}

    def _api_rows(self, parsed):
        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        source = (query.get("source") or [""])[0]
        if source == TOTAL_SOURCE:
            filters = self._filter_params(query)
            filters.pop("categories", None)  # 总账户的「分类」维度是来源多选
            filters["counted"] = self._parse_counted(query)
            filters["tags"] = _parse_list((query.get("tags") or [None])[0])
            raw_sources = (query.get("sources") or [None])[0]
            sources = _parse_list(raw_sources) if raw_sources else list(SOURCES)
            with self._connect() as conn:
                result = total.query_rows(
                    conn,
                    sort=(query.get("sort") or ["datetime"])[0],
                    order=(query.get("order") or ["desc"])[0],
                    page=_parse_int((query.get("page") or [None])[0], 1),
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
        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        source = (query.get("source") or [""])[0]
        if source == TOTAL_SOURCE:
            filters = self._filter_params(query)
            filters.pop("categories", None)
            filters["counted"] = self._parse_counted(query)
            filters["tags"] = _parse_list((query.get("tags") or [None])[0])
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
            if parsed.path == "/api/boc/convert":
                self._api_boc_convert_start()
            elif parsed.path == "/api/boc/convert/open-dir":
                self._api_boc_convert_open_dir()
            elif parsed.path == "/api/import/preview":
                self._api_import_preview()
            elif parsed.path == "/api/import/preview-batch":
                self._api_import_preview_batch()
            elif parsed.path == "/api/import/confirm":
                self._api_import_confirm()
            elif parsed.path == "/api/tags":
                self._api_tags_create()
            else:
                match = re.fullmatch(r"/api/boc/convert/([0-9a-f]{32})/preview", parsed.path)
                if match:
                    self._api_boc_convert_preview(match.group(1))
                else:
                    match = re.fullmatch(r"/api/boc/convert/([0-9a-f]{32})/confirm", parsed.path)
                    if match:
                        self._api_boc_convert_confirm(match.group(1))
                    else:
                        self._send_error(404, "Not Found")
        except ConflictError as exc:
            self._send(409, {"ok": False, "error": str(exc), "job_id": exc.job_id})
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
            if parsed.path == "/api/total/overrides":
                self._api_total_overrides()
            elif parsed.path == "/api/tags/apply":
                self._api_tags_apply()
            else:
                match = re.fullmatch(r"/api/tags/(\d+)", parsed.path)
                if match:
                    self._api_tags_update(int(match.group(1)))
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
            match = re.fullmatch(r"/api/tags/(\d+)", parsed.path)
            if match:
                self._api_tags_delete(int(match.group(1)))
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

        prepared = []
        for file_name, data in files:
            if len(data) > MAX_UPLOAD_BYTES:
                # 与单文件 _read_upload 口径一致：超限文件不解析、不写入
                prepared.append((file_name, data, "文件超过 64MB 上限"))
            elif Path(file_name).suffix.lower() not in ALLOWED_EXTENSIONS[source]:
                ext = Path(file_name).suffix.lower() or "无扩展名"
                prepared.append((file_name, data, f"{cfg.label} 只支持 {allowed} 文件（收到 {ext}）"))
            else:
                prepared.append((file_name, data, None))
        self._send(200, _batch_preview(cfg, source, prepared, existing))

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

    # ---- BOC PDF 转换 API ----

    def _api_boc_convert_start(self):
        """multipart 上传 PDF 列表 + 表单参数，落盘转换目录并启动后台任务。

        校验口径与批量导入一致：总大小 256MB / 单文件 64MB / 最多 50 个文件。
        已有任务运行中返回 409（附 job_id，前端直接衔接进行中的任务）。
        """
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            raise ApiError("请求体为空")
        if length > MAX_BATCH_UPLOAD_BYTES:
            raise ApiError("批量上传总大小超过 256MB 上限")
        files, form = _parse_convert_multipart(
            self.rfile.read(length), self.headers.get("Content-Type", "")
        )
        if not files:
            raise ApiError("未收到文件")
        if len(files) > MAX_BATCH_FILES:
            raise ApiError(f"一次最多转换 {MAX_BATCH_FILES} 个 PDF")

        scale = _parse_float(form.get("scale")) or 3.0
        device = form.get("device") or "auto"
        if device not in ("auto", "gpu", "cpu"):
            raise ApiError("推理设备必须是 auto / gpu / cpu")
        timeout_minutes = _parse_int(form.get("timeout_minutes"), 60, 1)
        force = form.get("force") in ("1", "true", "on", "yes")

        clean: List[Tuple[str, bytes]] = []
        seen_names = set()
        for raw_name, data in files:
            name = Path(raw_name).name  # 仅取文件名部分，防路径穿越
            if not name:
                continue
            if Path(name).suffix.lower() != ".pdf":
                raise ApiError(f"仅支持 PDF 文件：{name}")
            if len(data) > MAX_UPLOAD_BYTES:
                raise ApiError(f"文件超过 64MB 上限：{name}")
            key = name.lower()
            if key in seen_names:
                continue  # 同一次提交的同名文件取首个
            seen_names.add(key)
            clean.append((name, data))
        if not clean:
            raise ApiError("未收到有效的 PDF 文件")

        running = convert_jobs.current_running()
        if running is not None:
            raise ConflictError("已有转换任务进行中", running.id)

        for name, data in clean:
            (self.convert_dir / name).write_bytes(data)
        try:
            job = convert_jobs.start_job([name for name, _ in clean])
        except convert_jobs.JobBusy as exc:
            raise ConflictError(str(exc), exc.job_id)
        threading.Thread(
            target=convert_jobs.run_convert_job,
            args=(job, self.convert_dir, scale, device, timeout_minutes, force),
            daemon=True,
        ).start()
        self._send(200, {"ok": True, "job_id": job.id})

    def _api_boc_convert_status(self, job_id: str):
        """轮询任务进度；任务不存在（服务重启）返回 interrupted 供前端提示重来。"""
        job = convert_jobs.get_job(job_id)
        if job is None:
            self._send(200, {
                "ok": True,
                "status": "interrupted",
                "files": [],
                "totals": {"done": 0, "skipped": 0, "failed": 0, "transactions": 0},
                "started_at": None,
                "finished_at": None,
            })
            return
        self._send(200, {"ok": True, **job.snapshot()})

    def _require_finished_job(self, job_id: str):
        job = convert_jobs.get_job(job_id)
        if job is None:
            raise ApiError("转换任务不存在或已中断，请重新开始转换")
        if job.status == "running":
            raise ApiError("转换尚未完成")
        return job

    def _job_csv_files(self, job) -> List[Tuple[str, bytes]]:
        """任务成功产出的 CSV 列表 [(csv 文件名, bytes)]（失败/跳过的不纳入导入）。"""
        out: List[Tuple[str, bytes]] = []
        for f in job.files:
            if f.state != "done":
                continue
            csv_path = self.convert_dir / (Path(f.name).stem + ".csv")
            try:
                out.append((csv_path.name, csv_path.read_bytes()))
            except OSError:
                continue  # 产物缺失（极端情况）跳过
        return out

    def _api_boc_convert_preview(self, job_id: str):
        """读取任务成功产出的 CSV 做解析预览 + 去重比对（结构与 preview-batch 一致）。"""
        job = self._require_finished_job(job_id)
        csv_files = self._job_csv_files(job)
        if not csv_files:
            raise ApiError("没有可导入的 CSV（本次转换无成功产出）")
        cfg = SOURCE_CONFIGS[SOURCE_BOC]
        with self._connect() as conn:
            existing = db.existing_dedup_keys(conn, SOURCE_BOC)
        prepared = [(name, data, None) for name, data in csv_files]
        self._send(200, _batch_preview(cfg, SOURCE_BOC, prepared, existing))

    def _api_boc_convert_confirm(self, job_id: str):
        """逐文件 db.import_parse_result 写入 SQLite（幂等），返回逐文件与合并统计。

        可选 JSON 请求体 {"files": ["a.csv", ...]} 限定导入范围（前端预览移除文件时用）。
        """
        job = self._require_finished_job(job_id)
        csv_files = self._job_csv_files(job)
        if not csv_files:
            raise ApiError("没有可导入的 CSV（本次转换无成功产出）")
        body = self._optional_json()
        if body is not None:
            keep = {str(n) for n in (body.get("files") or [])}
            csv_files = [(n, d) for n, d in csv_files if n in keep]
            if not csv_files:
                raise ApiError("所选文件为空")

        results: List[dict] = []
        inserted = skipped = failed = 0
        with self._connect() as conn:
            for file_name, data in csv_files:
                try:
                    parsed = parse_file(SOURCE_BOC, file_name, data)
                except ParseError as exc:
                    results.append({
                        "file_name": file_name, "error": str(exc),
                        "inserted": 0, "skipped": 0, "failed": 0, "failures": [],
                    })
                    continue
                result = db.import_parse_result(conn, SOURCE_BOC, parsed, file_name)
                results.append({"file_name": file_name, "error": None, **result})
                inserted += result["inserted"]
                skipped += result["skipped"]
                failed += result["failed"]
        self._send(200, {
            "ok": True,
            "files": results,
            "inserted": inserted,
            "skipped": skipped,
            "failed": failed,
        })

    def _api_boc_convert_open_dir(self):
        """调起资源管理器打开转换目录。"""
        try:
            self.convert_dir.mkdir(parents=True, exist_ok=True)
            if os.name == "nt":
                os.startfile(str(self.convert_dir))
            else:
                subprocess.Popen(["xdg-open", str(self.convert_dir)])
        except OSError as exc:
            raise ApiError(f"打开目录失败：{exc}")
        self._send(200, {"ok": True})

    # ---- 收支属性 / 标签 API ----

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            raise ApiError("请求体为空")
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ApiError("请求体不是有效 JSON") from exc

    def _optional_json(self):
        """无请求体时返回 None（可选 JSON 参数接口用）。"""
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return None
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ApiError("请求体不是有效 JSON") from exc

    def _api_total_overrides(self):
        """批量设收支属性。方向约束铁律：只改计入/不计，永不反向。

        scope=ids    {"counted": 0, "scope": "ids", "ids": ["boc:1", ...]}
        scope=filter {"counted": 1, "scope": "filter", "filters": {...与 /api/rows 一致}}
        """
        body = self._read_json()
        counted = body.get("counted")
        if counted not in (0, 1, True, False):
            raise ApiError("counted 必须是 0 或 1")
        counted = int(bool(counted))
        with self._connect() as conn:
            keys = total.resolve_scope_rows(conn, body)
            updated = db.set_overrides(conn, keys, counted)
        self._send(200, {"ok": True, "updated": updated})

    def _api_tags(self):
        with self._connect() as conn:
            tags = db.list_tag_groups(conn)
        self._send(200, {"ok": True, "tags": tags})

    @staticmethod
    def _tag_name_of(body) -> str:
        name = (body.get("name") or "").strip()
        if not name:
            raise ApiError("标签名不能为空")
        return name

    def _api_tags_create(self):
        name = self._tag_name_of(self._read_json())
        with self._connect() as conn:
            tag = db.create_tag_group(conn, name)
        self._send(200, {"ok": True, "tag": tag})

    def _api_tags_update(self, tag_id: int):
        name = self._tag_name_of(self._read_json())
        with self._connect() as conn:
            tag = db.update_tag_group(conn, tag_id, name)
            if tag is None:
                raise ApiError("标签不存在")
        self._send(200, {"ok": True, "tag": tag})

    def _api_tags_delete(self, tag_id: int):
        with self._connect() as conn:
            if db.get_tag_group(conn, tag_id) is None:
                raise ApiError("标签不存在")
            db.delete_tag_group(conn, tag_id)
        self._send(200, {"ok": True})

    def _api_tags_apply(self):
        """批量打（add，幂等）/ 移除（remove）标签。scope 同 overrides。"""
        body = self._read_json()
        action = body.get("action")
        if action not in ("add", "remove"):
            raise ApiError("action 必须是 add 或 remove")
        raw_ids = body.get("group_ids") or []
        try:
            group_ids = [int(g) for g in raw_ids]
        except (TypeError, ValueError) as exc:
            raise ApiError("group_ids 必须是整数列表") from exc
        if not group_ids:
            raise ApiError("请选择标签")
        with self._connect() as conn:
            existing = {g["id"] for g in db.list_tag_groups(conn)}
            unknown = [g for g in group_ids if g not in existing]
            if unknown:
                raise ApiError(f"标签不存在：{unknown}")
            keys = total.resolve_scope_rows(conn, body)
            applied = db.apply_tags(conn, keys, group_ids, action)
        self._send(200, {"ok": True, "updated": applied})


def serve(db_path=None, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = False,
          convert_dir=None):
    """启动本地服务（阻塞）。db_path 默认当前目录下的 paycheck.db（相对启动目录）。

    convert_dir：BOC PDF 转换目录，默认 <paycheck.db 所在目录>/boc_csv（随库走）。
    """
    db_path = Path(db_path) if db_path else db.DEFAULT_DB_PATH
    db.init_db(db_path)

    convert_dir = Path(convert_dir) if convert_dir else db_path.parent / "boc_csv"
    convert_dir.mkdir(parents=True, exist_ok=True)

    Handler.db_path = db_path
    Handler.convert_dir = convert_dir
    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{httpd.server_port}/"
    print(f"账单工作台已启动：{url}")
    print(f"SQLite 数据库：{db_path}")
    print(f"PDF 转换目录：{convert_dir}")
    if open_browser:
        import webbrowser

        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        httpd.server_close()
