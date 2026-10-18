"""命令行入口：python -m paycheck_workbench / paycheck-workbench"""

from __future__ import annotations

import argparse

from paycheck_workbench import __version__, db


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="paycheck-workbench",
        description="账单工作台：BOC / 支付宝 / 微信账单的本地 HTML 展示与 SQLite 导入",
    )
    parser.add_argument("--db", default=None, help=f"SQLite 库文件路径（默认 {db.DEFAULT_DB_PATH}）")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1，本机使用）")
    parser.add_argument("--port", type=int, default=8765, help="监听端口（默认 8765）")
    parser.add_argument("--open", action="store_true", help="启动后自动打开浏览器")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    from paycheck_workbench.server import serve

    serve(db_path=args.db, host=args.host, port=args.port, open_browser=args.open)


if __name__ == "__main__":
    main()
