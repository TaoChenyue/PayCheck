"""PayCheck - 个人账单统计工具 (PySide6 GUI)"""

import os
import sys

# 静默 Qt 字体 OpenType 警告
os.environ["QT_LOGGING_RULES"] = "qt.text.font.db=false"

from PySide6.QtWidgets import QApplication
from paycheck.core.log import setup_logging
from paycheck.gui.main_window import MainWindow


def main():
    setup_logging(verbose=False)
    app = QApplication(sys.argv)
    app.setApplicationName("PayCheck")

    window = MainWindow()
    window.resize(1100, 800)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
