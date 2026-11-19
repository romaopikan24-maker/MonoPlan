import sys

from PyQt6.QtWidgets import QApplication

from main_window import MonoPlanWindow
from ui_widgets import MINIMALIST_QSS


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(MINIMALIST_QSS)
    window = MonoPlanWindow()
    window.show()
    sys.exit(app.exec())