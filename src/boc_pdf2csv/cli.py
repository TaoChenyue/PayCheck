"""boc-pdf2csv 命令行接口

用法:
    boc-pdf2csv ./statements/                    # 每个 PDF → 同名 CSV（已存在则跳过）
    boc-pdf2csv ./statements/ --force            # 强制重新导出（覆盖同名 CSV）
    boc-pdf2csv ./statements/ --scale 2.0        # 调整渲染精度
    boc-pdf2csv ./statements/ --timeout 120      # 延长超时
    boc-pdf2csv ./statements/ --device cpu       # 无 GPU 机器使用 CPU 推理
    boc-pdf2csv --version                        # 查看版本
    boc-pdf2csv --help                           # 帮助信息

文件日志: 写入 <输入目录>/boc-pdf2csv.log（1MB×3 轮转，--verbose 时升级 DEBUG），
只记文件名/条数/耗时等元数据，不记交易明细；控制台输出行为不变。
"""

import argparse
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from boc_pdf2csv import __version__
from boc_pdf2csv.pipeline import process_folder

_LOG_MAX_BYTES = 1024 * 1024
_LOG_BACKUP_COUNT = 3
_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
_CONSOLE_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def _setup_file_logging(folder_path: str, verbose: bool) -> None:
    """配置文件日志：写入 <输入目录>/boc-pdf2csv.log（1MB×3 轮转、UTF-8）。

    管线 logger（boc_pdf2csv.*）已有的 INFO/DEBUG 记录一并入文件；
    --verbose 时文件级别升级 DEBUG。propagate=False + 自有控制台 handler
    （格式与级别同 basicConfig），保证控制台行为与改动前完全一致：
    默认 WARNING、--verbose 时 DEBUG。打开失败（如输入目录不存在）时
    静默跳过：文件日志是辅助通道，不阻断转换。
    """
    try:
        handler = RotatingFileHandler(
            os.path.join(folder_path, "boc-pdf2csv.log"),
            maxBytes=_LOG_MAX_BYTES,
            backupCount=_LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
    except OSError:
        return
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(_CONSOLE_FORMAT, datefmt="%H:%M:%S"))
    console.setLevel(logging.DEBUG if verbose else logging.WARNING)
    logger = logging.getLogger("boc_pdf2csv")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.addHandler(handler)
    logger.addHandler(console)
    logger.propagate = False


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
        "--device",
        choices=["gpu", "cpu"],
        default="gpu",
        help="OCR 推理设备（默认: gpu，强制使用 GPU；无 GPU 机器可用 cpu）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制重新导出：同名 CSV 已存在时覆盖而不是跳过",
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

    # 配置日志：控制台保持现状（WARNING / --verbose 时 DEBUG）
    log_level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # 文件日志：写入 <输入目录>/boc-pdf2csv.log（管线 INFO 关键信息落盘）
    _setup_file_logging(args.input, args.verbose)

    try:
        result = process_folder(
            folder_path=args.input,
            scale=args.scale,
            timeout_minutes=args.timeout,
            verbose=args.verbose,
            device=args.device,
            force=args.force,
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
