import sys
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton
from PySide6.QtGui import QPainter, QColor, QFont
from PySide6.QtCore import Qt, QTimer

class CustomProgressBar(QWidget):
    def __init__(self, w_width):
        super().__init__()
        self.setMinimumSize(500, 50)
        self.w_width = w_width
        self.duration = 0
        self.trim_win_list = []

    def set_progress(self, value):
        self.trim_win_list = value
        self.update()

    def set_duration(self, value):
        self.duration = value
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Define trim area bar dimensions
        bar_width = self.w_width
        bar_height = 20
        bar_x = (self.width() - bar_width) / 2
        bar_y = (self.height() - bar_height) / 2

        # Draw the background of the trim area bar
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(200, 200, 200))
        painter.drawRect(bar_x, bar_y, bar_width, bar_height)

        # Draw the filled portion of the trim area bar
        for index in range(0, len(self.trim_win_list), 2):
            trim_start = self.trim_win_list[index]
            trim_end = self.trim_win_list[index+1]
            fill_start = int(bar_width * (trim_start / self.duration))
            fill_end = int(bar_width * (trim_end / self.duration))
            painter.setBrush(QColor(0, 160, 230))
            painter.drawRect(bar_x+fill_start, bar_y, fill_end-fill_start, bar_height)
