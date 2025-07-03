import sys 
from PyQt6.QtWidgets import QApplication
from .ui import MainWindow
from .debug_doc import generate_debug_doc

def main():
    generate_debug_doc()
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
