"""目录扫描模块 — 按子目录名自动发现账单文件和匹配 layout"""

import logging
import os
from dataclasses import dataclass, field
from typing import List, Dict

log = logging.getLogger("paycheck.scanner")


@dataclass
class BankFileGroup:
    """单个银行目录下的文件集合"""
    csv_files: List[str] = field(default_factory=list)
    pdf_files: List[str] = field(default_factory=list)


@dataclass
class ScanResult:
    """扫描结果"""
    wechat_files: List[str] = field(default_factory=list)
    ant_files: List[str] = field(default_factory=list)
    bank_groups: Dict[str, BankFileGroup] = field(default_factory=dict)
    # bank_groups 示例: {"boc": BankFileGroup(csvs=[...], pdfs=[...])}


def _walk_dir(dir_path: str) -> List[str]:
    """递归遍历目录，跳过 zip 子目录"""
    files = []
    for root, dirs, fnames in os.walk(dir_path):
        dirs[:] = [d for d in dirs if d.lower() != 'zip']
        for f in sorted(fnames):
            files.append(os.path.join(root, f))
    return files


def scan_directory(dir_path: str) -> ScanResult:
    """扫描输入目录，自动按子目录名归类文件

    发现规则:
      wechat/ → .xlsx (跳过 ~$ 临时文件)
      ant/    → .csv
      <其他名>/  → .csv 和 .pdf，以子目录名作为 bank group key
    """
    log.info("扫描目录: %s", dir_path)
    result = ScanResult()

    if not os.path.isdir(dir_path):
        log.warning("目录不存在: %s", dir_path)
        return result

    for entry in sorted(os.listdir(dir_path)):
        subdir = os.path.join(dir_path, entry)
        if not os.path.isdir(subdir):
            continue

        dirname = entry.lower()

        # 微信 - 只收 xlsx
        if dirname == "wechat":
            for f in _walk_dir(subdir):
                if f.endswith('.xlsx') and not os.path.basename(f).startswith('~$'):
                    result.wechat_files.append(f)
            log.info("微信: %d 个文件", len(result.wechat_files))
            continue

        # 支付宝 - 只收 csv
        if dirname == "ant":
            for f in _walk_dir(subdir):
                if f.lower().endswith('.csv'):
                    result.ant_files.append(f)
            log.info("支付宝: %d 个文件", len(result.ant_files))
            continue

        # 其他子目录（boc/、icbc/ 等）— 按目录名分组
        group = BankFileGroup()
        for f in _walk_dir(subdir):
            if f.lower().endswith('.csv'):
                group.csv_files.append(f)
            elif f.lower().endswith('.pdf'):
                group.pdf_files.append(f)

        if group.csv_files or group.pdf_files:
            result.bank_groups[dirname] = group
            log.info("银行[%s]: %d 个 CSV, %d 个 PDF", dirname,
                     len(group.csv_files), len(group.pdf_files))

    log.info("扫描完成: 微信%d, 支付宝%d, %d个银行组",
             len(result.wechat_files), len(result.ant_files),
             len(result.bank_groups))
    return result
