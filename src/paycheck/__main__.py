#!/usr/bin/env python3
"""
PayCheck - 个人账单统计工具

三阶段工作流:
    uv run paycheck pdf2image <input_dir>           # ① PDF → 图片
    uv run paycheck image2csv <bank_dir>            # ② 图片 → CSV
    uv run paycheck analyse <input_dir>              # ③ 分析 → 报表
"""

import argparse
import glob
import logging
import os
import re
import sys
import time

from paycheck.core.log import setup_logging


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="PayCheck - 个人账单统计工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  uv run paycheck pdf2image <input_dir>          # PDF → 图片
  uv run paycheck image2csv <bank_dir>           # 图片 → CSV
  uv run paycheck analyse <input_dir>            # 分析 → 报表
""",
    )
    sub = parser.add_subparsers(dest="command", help="可用命令")

    # ── pdf2image ──
    p_render = sub.add_parser(
        "pdf2image",
        help="PDF → 图片: 渲染 PDF 页面为裁剪后 PNG",
        description="扫描目录下的银行 PDF，逐页渲染 + 表格裁剪为 PNG 图片。",
    )
    p_render.add_argument("dir", help="输入目录（含银行子目录, 如 boc/）")
    p_render.add_argument("--scale", type=float, default=3.0, help="渲染倍率 (默认 3.0)")
    p_render.add_argument("-v", "--verbose", action="store_true", help="显示详细日志")

    # ── image2csv ──
    p_ocr = sub.add_parser(
        "image2csv",
        help="图片 → CSV: OCR 识别页面图片为结构化 CSV",
        description="扫描目录下的页面图片 (p*.png)，通过 OCR 识别为银行流水 CSV。",
    )
    p_ocr.add_argument("dir", help="图片目录（含 *_p*.png 文件）")
    p_ocr.add_argument("--layout", default=None, help="银行布局名称（默认从目录名推断）")
    p_ocr.add_argument("--scale", type=float, default=3.0, help="渲染倍率，需与 pdf2image 一致 (默认 3.0)")
    p_ocr.add_argument("--timeout", type=int, default=120, help="超时分钟数 (默认 120)")
    p_ocr.add_argument("--preview", action="store_true", help="预览模式: 只处理第一张图，输出 CSV 内容到终端，不写文件")
    p_ocr.add_argument("-v", "--verbose", action="store_true", help="显示详细日志")

    # ── analyse ──
    p_ana = sub.add_parser(
        "analyse",
        help="分析账单: 解析 → 聚合统计 → HTML 报表",
        description="解析已有 CSV/XLSX 账单文件，生成多维度 ECharts 分析报告。",
    )
    p_ana.add_argument("dir", help="输入目录（含 wechat/ ant/ 及银行子目录）")
    p_ana.add_argument("-o", "--output", default=None, help="输出 HTML 报表路径 (默认 report.html)")
    p_ana.add_argument("-v", "--verbose", action="store_true", help="显示详细日志")

    return parser


# =========================================================================
# 子命令处理
# =========================================================================


def _scan_bank_dirs(input_dir: str) -> dict:
    """扫描目录，返回 {layout_name: {"pdfs": [...], "csvs": [...]}}"""
    from paycheck.ingest.scanner import scan_directory

    result = scan_directory(input_dir)
    bank_groups = {}
    for name, group in result.bank_groups.items():
        bank_groups[name] = {"pdfs": group.pdf_files, "csvs": group.csv_files}
    return bank_groups


def _run_pdf2image(args) -> None:
    """pdf2image：PDF → 图片"""
    log = logging.getLogger("paycheck")
    from tqdm import tqdm
    from paycheck.ocr.pdf_render import pdf_to_images

    bank_groups = _scan_bank_dirs(args.dir)
    if not bank_groups:
        log.error("未找到银行 PDF 目录（需要子目录如 boc/）")
        sys.exit(1)

    log.info("银行子目录: %s", list(bank_groups.keys()))

    # 收集所有 PDF 路径
    pdfs_to_process = []
    for layout_name, group in bank_groups.items():
        pdfs_to_process.extend(group["pdfs"])

    total_all = len(pdfs_to_process)
    total_ok = 0

    with tqdm(total=total_all, desc="渲染 PDF", unit="PDF") as outer_pbar:
        for pdf_path in pdfs_to_process:
            out_dir = os.path.dirname(pdf_path)
            images = pdf_to_images(pdf_path, scale=args.scale, output_dir=out_dir)
            if images:
                total_ok += 1
            outer_pbar.update(1)

    if total_ok < total_all:
        log.warning("完成: %d / %d 个 PDF 渲染成功", total_ok, total_all)
    else:
        log.info("完成: 所有 %d 个 PDF 渲染成功", total_ok)


def _run_image2csv(args) -> None:
    """image2csv：图片 → CSV"""
    log = logging.getLogger("paycheck")
    from paycheck.ocr.pipeline import images_to_csv

    input_dir = args.dir
    if not os.path.isdir(input_dir):
        log.error("目录不存在: %s", input_dir)
        sys.exit(1)

    # 推断 layout 名称（从目录名或 --layout 参数）
    layout_name = args.layout
    if not layout_name:
        layout_name = os.path.basename(os.path.normpath(input_dir)).lower()
        log.info("从目录名推断布局: %s", layout_name)

    # 扫描子目录下 p*.png 图片（新结构: {stem}/p{N}.png）
    pattern = os.path.join(input_dir, "**", "p*.png")
    all_images = sorted(glob.glob(pattern, recursive=True))
    if not all_images:
        log.error("未找到页面图片 (p*.png) in %s", input_dir)
        sys.exit(1)

    # ── preview 模式：只处理第一张图，输出 CSV 到终端 ──
    if args.preview:
        log.info("预览模式: 仅处理第一张图")
        all_images = all_images[:1]

    # 按父目录名（PDF stem）分组
    groups = {}
    for img_path in all_images:
        parent_dir = os.path.basename(os.path.dirname(img_path))
        filename = os.path.basename(img_path)
        m = re.match(r'p(\d+)\.png$', filename)
        if not m:
            continue
        page = int(m.group(1))
        groups.setdefault(parent_dir, []).append((page, img_path))

    if not groups:
        log.error("未找到符合命名规范的页面图片 (p*.png)")
        sys.exit(1)

    log.info("找到 %d 组图片: %s", len(groups), list(groups.keys()))
    log.info("布局: %s | 倍率: %.1f", layout_name, args.scale)

    ok_count = 0
    for base_name, pages in sorted(groups.items()):
        pages.sort(key=lambda x: x[0])
        image_paths = [p[1] for p in pages]
        expected_csv = os.path.join(input_dir, f"{base_name}.csv")

        if not args.preview and os.path.isfile(expected_csv):
            log.info("  CSV 已存在: %s", os.path.basename(expected_csv))
            ok_count += 1
            continue

        log.info("  OCR: %s (%d 页)", base_name, len(image_paths))
        if args.preview:
            exit_code = images_to_csv(
                image_paths,
                layout_name,
                scale=args.scale,
                timeout_minutes=args.timeout,
                preview=True,
            )
        else:
            exit_code = images_to_csv(
                image_paths,
                layout_name,
                scale=args.scale,
                output_path=expected_csv,
                timeout_minutes=args.timeout,
            )
        if exit_code == 0:
            label = "预览" if args.preview else os.path.basename(expected_csv)
            log.info("  ✓ %s", label)
            ok_count += 1
        else:
            log.warning("  ⚠ OCR 失败: %s", base_name)

    if ok_count < len(groups):
        log.warning("完成: %d / %d 组合成功", ok_count, len(groups))
    else:
        log.info("完成: 所有 %d 组合成功", ok_count)


def _run_analyse(args) -> None:
    """analyse：解析 → 聚合 → 报表"""
    log = logging.getLogger("paycheck")
    from paycheck.ingest.scanner import scan_directory
    from paycheck.ingest.parsers import parse_file
    from paycheck.analysis.stats import aggregate
    from paycheck.report.html_reporter import generate_html

    output_path = args.output or "report.html"

    log.info("扫描目录: %s", args.dir)
    result = scan_directory(args.dir)

    bank_layouts = list(result.bank_groups.keys())
    log.info("微信: %d 个文件 | 支付宝: %d 个文件 | 银行: %s",
             len(result.wechat_files), len(result.ant_files), bank_layouts)

    if not result.wechat_files and not result.ant_files and not result.bank_groups:
        log.error("未找到任何账单文件（需要 wechat/、ant/ 或银行子目录）")
        sys.exit(1)

    # ── 解析 ──
    all_transactions = []

    for f in result.wechat_files:
        try:
            txns = parse_file(f)
            log.info("  微信: %s — %d 条", os.path.basename(f), len(txns))
            all_transactions.extend(txns)
        except Exception as e:
            log.warning("  微信解析失败: %s — %s", os.path.basename(f), e)

    for f in result.ant_files:
        try:
            txns = parse_file(f)
            log.info("  支付宝: %s — %d 条", os.path.basename(f), len(txns))
            all_transactions.extend(txns)
        except Exception as e:
            log.warning("  支付宝解析失败: %s — %s", os.path.basename(f), e)

    for layout_name, group in result.bank_groups.items():
        for f in group.csv_files:
            try:
                txns = parse_file(f)
                log.info("  [%s]: %s — %d 条", layout_name, os.path.basename(f), len(txns))
                all_transactions.extend(txns)
            except Exception as e:
                log.warning("  [%s] 解析失败: %s — %s", layout_name, os.path.basename(f), e)

    if not all_transactions:
        log.error("未能解析到任何交易记录（PDF 未预处理？先运行 paycheck pdf2csv）")
        sys.exit(1)

    platform_counts = {}
    for t in all_transactions:
        platform_counts[t.platform] = platform_counts.get(t.platform, 0) + 1
    platform_str = " | ".join(f"{k}: {v}条" for k, v in sorted(platform_counts.items()))
    log.info("共 %d 条交易记录 (%s)", len(all_transactions), platform_str)

    # ── 聚合 ──
    log.info("开始聚合统计...")
    data = aggregate(all_transactions)
    s = data["summary"]
    total_expense = f"{s['total_expense']:,.2f}"
    wechat_total = f"{s['wechat_total']:,.2f}"
    alipay_total = f"{s['alipay_total']:,.2f}"
    bank_total = f"{s.get('bank_total', 0):,.2f}"
    log.info("  总支出: %s (%d 笔)", total_expense, s["total_count"])
    log.info("  微信: %s | 支付宝: %s | 银行: %s",
             wechat_total, alipay_total, bank_total)

    # ── 报表 ──
    log.info("生成报表...")
    html = generate_html(data)
    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    log.info("报表已生成: %s", output_path)


def cli():
    parser = _build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if not os.path.exists(args.dir):
        print(f"错误: 目录不存在: {args.dir}", file=sys.stderr)
        sys.exit(1)

    # ── 初始化日志（先于其他 import，以压制第三方库噪声）──
    setup_logging(verbose=args.verbose)
    log = logging.getLogger("paycheck")

    start_time = time.time()

    handlers = {
        "pdf2image": _run_pdf2image,
        "image2csv": _run_image2csv,
        "analyse": _run_analyse,
    }

    handler = handlers.get(args.command)
    if handler:
        handler(args)
    else:
        log.error("未知命令: %s", args.command)
        sys.exit(1)

    elapsed = time.time() - start_time
    log.info("完成！耗时 %.1fs", elapsed)


if __name__ == "__main__":
    cli()
