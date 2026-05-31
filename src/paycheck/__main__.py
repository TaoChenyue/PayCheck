#!/usr/bin/env python3
"""
PayCheck - 个人账单统计工具

用法:
    uv run paycheck --dir resource/
    uv run paycheck --dir resource/ -o my_report.html --verbose
"""

import argparse
import logging
import os
import sys
import time

from paycheck.core.log import setup_logging


def cli():
    parser = argparse.ArgumentParser(
        description="PayCheck - 个人账单统计工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  uv run paycheck --dir resource/
  uv run paycheck --dir resource/ --verbose
  uv run paycheck --dir resource/ -o my_report.html
""",
    )
    parser.add_argument("--dir", default=None, help="输入目录（含 wechat/ant/boc 等子目录）")
    parser.add_argument("-o", "--output", default=None, help="输出 HTML 报表路径")
    parser.add_argument("--scale", type=float, default=3.0, help="PDF 渲染倍率 (默认 3.0)")
    parser.add_argument("--timeout", type=int, default=120, help="超时分钟数 (默认 120)")
    parser.add_argument("-v", "--verbose", action="store_true", help="在控制台显示详细日志")

    args = parser.parse_args()
    input_dir = args.dir

    # ── 初始化日志（先于其他 import，以压制第三方库噪声）──
    setup_logging(verbose=args.verbose)
    log = logging.getLogger("paycheck")

    if not input_dir:
        log.error("未指定输入目录 (--dir)")
        parser.print_help()
        sys.exit(1)

    if not os.path.exists(input_dir):
        log.error("目录不存在: %s", input_dir)
        sys.exit(1)

    # ── 延迟 import（避免第三方库在日志配置前输出）──
    from paycheck.ingest.scanner import scan_directory
    from paycheck.ingest.parsers import parse_file
    from paycheck.ocr.pipeline import pdf_to_csv
    from paycheck.analysis.stats import aggregate
    from paycheck.report.html_reporter import generate_html

    output_path = args.output or "report.html"
    start_time = time.time()

    # ── 扫描 ──
    log.info("扫描目录: %s", input_dir)
    result = scan_directory(input_dir)

    bank_layouts = list(result.bank_groups.keys())
    log.info("微信: %d 个文件 | 支付宝: %d 个文件 | 银行: %s",
             len(result.wechat_files), len(result.ant_files), bank_layouts)

    if not result.wechat_files and not result.ant_files and not result.bank_groups:
        log.error("未找到任何账单文件（需要 wechat/、ant/ 或银行子目录）")
        sys.exit(1)

    # ── 银行 PDF → OCR → CSV ──
    for layout_name, group in result.bank_groups.items():
        for pdf_path in group.pdf_files:
            expected_csv = os.path.splitext(pdf_path)[0] + ".csv"
            if os.path.isfile(expected_csv):
                log.info("  CSV 已存在: %s", os.path.basename(expected_csv))
                if expected_csv not in group.csv_files:
                    group.csv_files.append(expected_csv)
                continue

            log.info("  OCR [%s]: %s", layout_name, os.path.basename(pdf_path))
            exit_code = pdf_to_csv(pdf_path, layout_name, args.scale, expected_csv, args.timeout)
            if exit_code == 0 and os.path.isfile(expected_csv):
                log.info("  ✓ OCR 完成: %s", os.path.basename(expected_csv))
                group.csv_files.append(expected_csv)
            else:
                log.warning("  ⚠ OCR 失败，跳过: %s", os.path.basename(pdf_path))

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
        log.error("未能解析到任何交易记录")
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
    log.info("  总支出: %,.2f (%d 笔)", s["total_expense"], s["total_count"])
    log.info("  微信: %,.2f | 支付宝: %,.2f | 银行: %,.2f",
             s["wechat_total"], s["alipay_total"], s.get("bank_total", 0))

    # ── 报表 ──
    log.info("生成报表...")
    html = generate_html(data)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    log.info("报表已生成: %s", output_path)

    elapsed = time.time() - start_time
    log.info("完成！耗时 %.1fs。打开 %s 查看报表", elapsed, output_path)


if __name__ == "__main__":
    cli()
