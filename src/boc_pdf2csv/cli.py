"""boc-pdf2csv 命令行接口

用法:
    boc-pdf2csv ./statements/                    # 每个 PDF → 同名 CSV（已存在则跳过）
    boc-pdf2csv ./statements/ --scale 2.0        # 调整渲染精度
    boc-pdf2csv ./statements/ --timeout 120      # 延长超时
    boc-pdf2csv --version                        # 查看版本
    boc-pdf2csv --help                           # 帮助信息
"""

import argparse
import logging
import os
import sys

from boc_pdf2csv import __version__
from boc_pdf2csv.pipeline import process_folder


def main() -> int:
    """CLI 入口，返回退出码"""
    parser = argparse.ArgumentParser(
        prog="boc-pdf2csv",
        description="将中国银行 PDF 对账单转换为 CSV 文件",
    )
    parser.add_argument(
        "input",
        help="包含 PDF 文件的文件夹路径",
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=3.0,
        help="PDF 渲染倍率（默认: 3.0）",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="单个 PDF 超时分钟数（默认: 60）",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="详细日志输出",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"boc-pdf2csv {__version__}",
    )
    args = parser.parse_args()

    # 配置日志
    log_level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        result = process_folder(
            folder_path=args.input,
            scale=args.scale,
            timeout_minutes=args.timeout,
            verbose=args.verbose,
        )
    except NotADirectoryError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1

    except FileNotFoundError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 2

    except RuntimeError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 3

    except Exception as e:
        print(f"未预期的错误: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 3

    # 汇总输出
    print(
        f"完成: {len(result.processed)} 个 PDF → CSV, "
        f"跳过 {len(result.skipped)} 个, 失败 {len(result.failed)} 个, "
        f"共 {result.total_transactions} 条交易"
    )

    if result.failed:
        for pdf_path in result.failed:
            print(f"警告: 处理失败: {os.path.basename(pdf_path)}", file=sys.stderr)

    if result.processed and result.total_transactions == 0:
        # 全部 CSV 仅有表头，无交易数据
        print("警告: 未提取到任何交易记录", file=sys.stderr)
        return 4

    return 0


if __name__ == "__main__":
    sys.exit(main())
