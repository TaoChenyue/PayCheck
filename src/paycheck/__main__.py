#!/usr/bin/env python3
"""
PayCheck - 个人账单统计工具

用法:
    uv run paycheck --dir resource/
    uv run paycheck --dir resource/ -o my_report.html
    python -m paycheck --dir resource/
"""

import argparse
import os
import sys
import time

from paycheck.ingest.scanner import scan_directory
from paycheck.ingest.parsers import parse_file
from paycheck.ocr.pipeline import pdf_to_csv
from paycheck.analysis.stats import aggregate
from paycheck.report.html_reporter import generate_html


def cli():
    parser = argparse.ArgumentParser(
        description="PayCheck - 个人账单统计工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  uv run paycheck --dir resource/
  uv run paycheck --dir resource/ -o my_report.html
""",
    )
    parser.add_argument("--dir", default=None, help="输入目录（含 wechat/ant/boc 等子目录）")
    parser.add_argument("-o", "--output", default=None, help="输出 HTML 报表路径")
    parser.add_argument("--scale", type=float, default=3.0, help="PDF 渲染倍率 (默认 3.0)")
    parser.add_argument("--timeout", type=int, default=120, help="超时分钟数 (默认 120)")

    args = parser.parse_args()

    input_dir = args.dir
    if not input_dir:
        parser.print_help()
        sys.exit(1)

    output_path = args.output or "report.html"

    if not os.path.exists(input_dir):
        print(f"错误: 目录不存在 - {input_dir}")
        sys.exit(1)

    start_time = time.time()
    print(f"扫描目录: {input_dir}")
    result = scan_directory(input_dir)

    bank_layouts = list(result.bank_groups.keys())
    print(f"   微信文件: {len(result.wechat_files)} | 支付宝文件: {len(result.ant_files)} | 银行目录: {bank_layouts}")

    if not result.wechat_files and not result.ant_files and not result.bank_groups:
        print("错误: 未找到任何账单文件（需要 wechat/、ant/ 或银行子目录）")
        sys.exit(1)

    # --- 银行 PDF 自动 OCR ---
    for layout_name, group in result.bank_groups.items():
        for pdf_path in group.pdf_files:
            expected_csv = os.path.splitext(pdf_path)[0] + ".csv"
            if os.path.isfile(expected_csv):
                print(f"  CSV 已存在: {os.path.basename(expected_csv)}")
                if expected_csv not in group.csv_files:
                    group.csv_files.append(expected_csv)
                continue

            print(f"  OCR 识别 [{layout_name}]: {os.path.basename(pdf_path)} ... ", end="", flush=True)
            try:
                exit_code = pdf_to_csv(pdf_path, layout_name, args.scale, expected_csv, args.timeout)
                if exit_code == 0 and os.path.isfile(expected_csv):
                    print("完成")
                    group.csv_files.append(expected_csv)
                else:
                    print(f"失败 (exit={exit_code})")
            except Exception as e:
                print(f"失败: {e}")

    # --- 解析 ---
    all_transactions = []

    for f in result.wechat_files:
        print(f"  解析微信账单: {os.path.basename(f)}... ", end="")
        try:
            txns = parse_file(f)
            print(f"{len(txns)} 条记录")
            all_transactions.extend(txns)
        except Exception as e:
            print(f"失败: {e}")

    for f in result.ant_files:
        print(f"  解析支付宝账单: {os.path.basename(f)}... ", end="")
        try:
            txns = parse_file(f)
            print(f"{len(txns)} 条记录")
            all_transactions.extend(txns)
        except Exception as e:
            print(f"失败: {e}")

    for layout_name, group in result.bank_groups.items():
        for f in group.csv_files:
            print(f"  解析[{layout_name}]账单: {os.path.basename(f)}... ", end="")
            try:
                txns = parse_file(f)
                print(f"{len(txns)} 条记录")
                all_transactions.extend(txns)
            except Exception as e:
                print(f"失败: {e}")

    if not all_transactions:
        print("错误: 未能解析到任何交易记录")
        sys.exit(1)

    platform_counts = {}
    for t in all_transactions:
        platform_counts[t.platform] = platform_counts.get(t.platform, 0) + 1
    platform_str = " | ".join(f"{k}: {v}条" for k, v in sorted(platform_counts.items()))
    print(f"\n共 {len(all_transactions)} 条交易记录 ({platform_str})")

    # --- 聚合 ---
    print("开始聚合统计...")
    data = aggregate(all_transactions)
    s = data["summary"]
    print(f"   总支出: {s['total_expense']:,.2f} ({s['total_count']} 笔)")
    print(f"   微信: {s['wechat_total']:,.2f} | 支付宝: {s['alipay_total']:,.2f} | 银行: {s.get('bank_total', 0):,.2f}")

    # --- 报表 ---
    print("生成报表...")
    html = generate_html(data)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  报表已生成: {output_path}")

    elapsed = time.time() - start_time
    print(f"\n完成！耗时 {elapsed:.1f}s。打开 {output_path} 查看报表")


if __name__ == "__main__":
    cli()
