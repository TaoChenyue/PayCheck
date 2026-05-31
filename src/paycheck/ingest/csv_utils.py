"""CSV 行解析工具 — 处理引号包裹的字段"""

from typing import List


def parse_csv_line(line: str) -> List[str]:
    """解析单行 CSV，正确处理引号包裹的字段"""
    result = []
    current = ""
    in_quotes = False
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == '"':
            if in_quotes and i + 1 < len(line) and line[i + 1] == '"':
                current += '"'
                i += 1
            else:
                in_quotes = not in_quotes
        elif ch == ',' and not in_quotes:
            result.append(current)
            current = ""
        else:
            current += ch
        i += 1
    result.append(current)
    return result
