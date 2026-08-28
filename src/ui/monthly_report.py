from calendar import monthrange
from collections import defaultdict
from copy import deepcopy
from datetime import datetime
import re

from PyQt6.QtCore import Qt, QTimer, QPointF
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QFrame, QGridLayout
)


class MonthlyReportWidget(QWidget):
    """Monthly ASP/CPU report styled like a monitoring dashboard, with charts and summary cards."""

    @staticmethod
    def _normalize_server_name(value):
        if value is None:
            return ""
        text = str(value).strip()
        if not text or text.lower() in {"n/a", "none", "unknown"}:
            return ""
        if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", text):
            return ""
        return text

    class MetricChartWidget(QWidget):
        def __init__(self, metric_name, parent=None):
            super().__init__(parent)
            self.metric_name = metric_name
            self.mode = "day"
            self.series = []
            self.lines = []
            self.days = []
            self.max_value = 100.0
            self.min_value = 0.0
            self.base_colors = [
                "#3b82f6", "#f59e0b", "#10b981", "#a78bfa", "#f97316",
                "#34d399", "#f87171", "#60a5fa", "#f9a8d4", "#c084fc"
            ]

        def set_data(self, report_rows, days, current_month):
            values_by_server = []
            for row in report_rows:
                server = row.get("server")
                day_map = row.get("day_map", {})
                series = []
                for day in days:
                    value = day_map.get(day)
                    series.append(float(value) if value is not None else 0.0)
                values_by_server.append((server, series, row.get("month_avg", 0.0)))

            self.series = values_by_server
            self.days = list(days)
            self.current_month = current_month
            self.max_value = max(100.0, max((v for _, series, _ in self.series for v in series), default=100.0) * 1.15)
            self.min_value = 0.0
            self.update()

        def paintEvent(self, event):
            painter = QPainter(self)
            try:
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.fillRect(self.rect(), QColor("#f8fafc"))

                rect = self.rect().adjusted(10, 12, -10, -10)
                left = rect.left() + 26
                right = rect.right() - 8
                top = rect.top() + 18
                bottom = rect.bottom() - 24

                if not self.series or not self.days:
                    painter.setPen(QPen(QColor("#94a3b8"), 1))
                    painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No data available")
                    return

                painter.setPen(QPen(QColor("#cbd5e1"), 1))
                for grid in range(0, 6):
                    y = int(top + (bottom - top) * (grid / 5.0))
                    painter.drawLine(left, y, right, y)

                x_step = (right - left) / max(1, len(self.days) - 1 if len(self.days) > 1 else 1)
                for idx, day in enumerate(self.days):
                    x = left + (x_step * idx if len(self.days) > 1 else 0)
                    if idx < len(self.days) - 1:
                        painter.drawLine(x, top, x, bottom)

                for server_index, (name, series, _) in enumerate(self.series):
                    points = []
                    for idx, value in enumerate(series):
                        if len(self.days) > 1:
                            x = left + (right - left) * idx / max(1, len(self.days) - 1)
                        else:
                            x = left
                        y = bottom - ((value - self.min_value) / max(1e-6, self.max_value - self.min_value)) * (bottom - top)
                        points.append(QPointF(x, y))
                    color = QColor(self.base_colors[server_index % len(self.base_colors)])
                    painter.setPen(QPen(color, 2.2))
                    if len(points) == 1:
                        painter.drawPoint(points[0])
                    else:
                        painter.drawPolyline(QPolygonF(points))

                painter.setPen(QPen(QColor("#6b7280"), 1))
                for idx, day in enumerate(self.days):
                    x = left + (x_step * idx if len(self.days) > 1 else 0)
                    if day % max(2, int(len(self.days) / 6)) == 0 or idx == len(self.days) - 1:
                        painter.drawText(int(x) - 10, bottom + 18, 24, 16, Qt.AlignmentFlag.AlignCenter, str(day))

                painter.setPen(QPen(QColor("#6b7280"), 1))
                for idx in range(6):
                    value = self.max_value - ((self.max_value - self.min_value) * idx / 5.0)
                    y = top + (bottom - top) * (idx / 5.0)
                    painter.drawText(0, int(y) - 6, 30, 16, Qt.AlignmentFlag.AlignRight, f"{value:.0f}")

                painter.setPen(QPen(QColor("#7c8aa0"), 1))
                painter.drawLine(left, top, left, bottom)
                painter.drawLine(left, bottom, right, bottom)

                start_x = left + 8
                legend_y = top - 8
                for idx, (name, _, _) in enumerate(self.series[:8]):
                    color = QColor(self.base_colors[idx % len(self.base_colors)])
                    painter.setPen(QPen(color, 2.5))
                    painter.drawLine(start_x, legend_y, start_x + 14, legend_y)
                    painter.setPen(QPen(QColor("#334155"), 1))
                    painter.drawText(start_x + 18, legend_y + 5, 64, 12, Qt.AlignmentFlag.AlignLeft, name[:7])
                    start_x += 80
            finally:
                painter.end()

    class SummaryCard(QWidget):
        def __init__(self, title, value, subtitle, parent=None):
            super().__init__(parent)
            self.setFixedHeight(72)
            self.title = QLabel(title)
            self.title.setFont(QFont("Segoe UI", 9))
            self.title.setStyleSheet("color: #6b7280; background: transparent;")
            self.value = QLabel(value)
            self.value.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
            self.value.setStyleSheet("color: #1f2937; background: transparent;")
            self.subtitle = QLabel(subtitle)
            self.subtitle.setFont(QFont("Segoe UI", 8))
            self.subtitle.setStyleSheet("color: #6b7280; background: transparent;")
            layout = QVBoxLayout(self)
            layout.setContentsMargins(12, 10, 12, 10)
            layout.setSpacing(2)
            layout.addWidget(self.title)
            layout.addWidget(self.value)
            layout.addWidget(self.subtitle)

        def set_theme(self, is_dark_theme):
            if is_dark_theme:
                self.setStyleSheet("QWidget { background-color: #161b22; border: 1px solid #30363d; border-radius: 8px; } QLabel { color: #e5e7eb; background: transparent; }")
            else:
                self.setStyleSheet("QWidget { background-color: #ffffff; border: 1px solid #d0d7de; border-radius: 8px; } QLabel { color: #1f2937; background: transparent; }")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_dark_theme = True
        self.log_data_store = {}
        self.parent_log_viewer = None
        self.source_mode = "local"
        self.last_sync_at = None
        self._sync_in_progress = False

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(16, 16, 16, 16)
        self.main_layout.setSpacing(12)

        header = QHBoxLayout()
        self.title_label = QLabel("IBM i Monthly ASP/CPU Report")
        self.title_label.setFont(self._make_font("Segoe UI", 14, QFont.Weight.Bold))
        self.title_label.setStyleSheet("color: #ffffff;")
        header.addWidget(self.title_label)
        header.addStretch()

        self.month_combo = QComboBox()
        self.month_combo.setFixedWidth(150)
        self.month_combo.currentIndexChanged.connect(self.refresh_report)
        header.addWidget(self.month_combo)

        self.sync_button = QPushButton("Sync")
        self.sync_button.setFixedWidth(90)
        self.sync_button.clicked.connect(self.sync_online)
        header.addWidget(self.sync_button)
        self.main_layout.addLayout(header)

        self.sync_status_label = QLabel("Source: Local persisted data")
        self.sync_status_label.setFont(self._make_font("Segoe UI", 9, QFont.Weight.Normal))
        self.sync_status_label.setStyleSheet("color: #8b949e;")
        self.main_layout.addWidget(self.sync_status_label)

        self.last_sync_label = QLabel("Last sync: Never")
        self.last_sync_label.setFont(self._make_font("Segoe UI", 9, QFont.Weight.Normal))
        self.last_sync_label.setStyleSheet("color: #8b949e;")
        self.main_layout.addWidget(self.last_sync_label)

        self.summary_label = QLabel("Averages are calculated from the 1st to the last day of the selected month.")
        self.summary_label.setFont(self._make_font("Segoe UI", 9, QFont.Weight.Normal))
        self.summary_label.setStyleSheet("color: #8b949e;")
        self.main_layout.addWidget(self.summary_label)

        self.cpu_panel = self._build_metric_section("CPU")
        self.asp_panel = self._build_metric_section("ASP")
        self.main_layout.addWidget(self.cpu_panel)
        self.main_layout.addWidget(self.asp_panel)

        self.set_theme(self.is_dark_theme)
        self.load_month_options()
        self.refresh_report()

    def _build_metric_section(self, metric_name):
        section = QWidget()
        section_layout = QHBoxLayout(section)
        section_layout.setContentsMargins(0, 0, 0, 0)
        section_layout.setSpacing(14)

        left_panel = QWidget()
        left_panel.setMinimumHeight(260)
        left_panel.setStyleSheet("background-color: #f8fafc; border: 1px solid #d0d7de; border-radius: 10px;")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(10, 10, 10, 8)
        left_layout.setSpacing(6)

        top_row = QHBoxLayout()
        metric_label = QLabel(f"{metric_name} Usage")
        metric_label.setFont(self._make_font("Segoe UI", 11, QFont.Weight.Bold))
        metric_label.setStyleSheet("color: #1f2937;")
        top_row.addWidget(metric_label)
        top_row.addStretch()

        button_group = QWidget()
        button_layout = QHBoxLayout(button_group)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(3)
        for label in ["Day", "Week", "Month"]:
            btn = QPushButton(label)
            btn.setFixedHeight(24)
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            if label == "Day":
                btn.setChecked(True)
            btn.clicked.connect(lambda _, key=f"{metric_name}:{label}": self._on_toggle_change(key))
            button_layout.addWidget(btn)
        top_row.addWidget(button_group)
        left_layout.addLayout(top_row)

        chart = self.MetricChartWidget(metric_name)
        left_layout.addWidget(chart, stretch=1)
        section_layout.addWidget(left_panel, stretch=3)

        right_panel = QWidget()
        right_panel.setMinimumWidth(230)
        right_panel.setStyleSheet("background-color: transparent;")
        right_panel_layout = QVBoxLayout(right_panel)
        right_panel_layout.setContentsMargins(0, 0, 0, 0)
        right_panel_layout.setSpacing(8)

        card_container = QWidget()
        card_layout = QVBoxLayout(card_container)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(8)

        self._summary_cards = getattr(self, '_summary_cards', {})
        self._summary_cards[metric_name] = {
            "average": self.SummaryCard("Month Avg", "0.00%", "0 days trend", card_container),
            "servers": QWidget(),
            "chart": chart,
        }

        self._summary_cards[metric_name]["average"].set_theme(self.is_dark_theme)
        card_layout.addWidget(self._summary_cards[metric_name]["average"])

        self._summary_cards[metric_name]["servers"] = QWidget()
        server_layout = QVBoxLayout()
        server_layout.setContentsMargins(0, 0, 0, 0)
        server_layout.setSpacing(6)
        server_layout = self._replace_layout(
            self._summary_cards[metric_name]["servers"],
            server_layout,
        )
        self._summary_cards[metric_name]["servers"].setStyleSheet("background-color: transparent;")
        card_layout.addWidget(self._summary_cards[metric_name]["servers"])
        right_panel_layout.addWidget(card_container)
        section_layout.addWidget(right_panel, stretch=1)

        setattr(self, f"{metric_name.lower()}_chart", chart)
        setattr(self, f"{metric_name.lower()}_summary_card", self._summary_cards[metric_name]["average"])
        return section

    def _on_toggle_change(self, key):
        metric_name, mode = key.split(":", 1)
        if metric_name == "CPU":
            self.cpu_chart.mode = mode.lower()
        elif metric_name == "ASP":
            self.asp_chart.mode = mode.lower()
        self.refresh_report()

    def _make_font(self, family="Segoe UI", point_size=9, weight=QFont.Weight.Normal):
        font = QFont(family)
        try:
            size_value = int(point_size)
        except (TypeError, ValueError):
            size_value = 9
        font.setPointSize(max(1, size_value))
        font.setWeight(weight)
        return font

    def _clear_layout(self, layout):
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
            nested_layout = item.layout()
            if nested_layout is not None:
                self._clear_layout(nested_layout)
                nested_layout.deleteLater()
    def _replace_layout(self, widget, layout):
        old_layout = widget.layout()
        if old_layout is not None and old_layout is not layout:
            self._clear_layout(old_layout)
            return old_layout
        if old_layout is None:
            widget.setLayout(layout)
        return layout

    def set_log_data_store(self, log_data_store, source_mode=None):
        self.log_data_store = log_data_store if log_data_store is not None else {}
        if source_mode is not None:
            self.source_mode = source_mode
        self.load_month_options()
        self.sync_status_label.setText(
            "Source: Online sync" if self.source_mode == "online" else "Source: Local persisted data"
        )
        if self.isVisible():
            self.refresh_report()

    def set_last_sync_timestamp(self, timestamp=None):
        self.last_sync_at = timestamp
        if timestamp is None:
            text = "Last sync: Never"
        else:
            text = f"Last sync: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
        self.last_sync_label.setText(text)

    def sync_online(self):
        if self._sync_in_progress:
            return
        self._sync_in_progress = True
        self.sync_button.setEnabled(False)
        try:
            if self.parent_log_viewer is not None:
                firebase_store = getattr(
                    self.parent_log_viewer,
                    "firebase_log_data_store",
                    {},
                )
                report_store = deepcopy(firebase_store)
                # A sync can happen while the background loaders are still empty.
                # Keep the current report until data is actually available.
                if report_store:
                    self.set_log_data_store(report_store, source_mode="online")
                self.set_last_sync_timestamp(datetime.now())
                return

            self.source_mode = "online"
            self.sync_status_label.setText("Source: Online sync")
            self.set_last_sync_timestamp(datetime.now())
            if self.isVisible():
                self.refresh_report()
        finally:
            self._sync_in_progress = False
            self.sync_button.setEnabled(True)

    def set_theme(self, is_dark_theme):
        self.is_dark_theme = is_dark_theme
        bg = "#0d1117" if is_dark_theme else "#f6f8fa"
        panel = "#161b22" if is_dark_theme else "#ffffff"
        text = "#c9d1d9" if is_dark_theme else "#1f2328"
        muted = "#8b949e" if is_dark_theme else "#57606a"
        border = "#30363d" if is_dark_theme else "#d0d7de"
        self.setStyleSheet(f"QWidget {{ background-color: {bg}; color: {text}; }} QLabel {{ color: {text}; }} QComboBox {{ background-color: {panel}; color: {text}; border: 1px solid {border}; padding: 4px 8px; }} QPushButton {{ background-color: {panel}; color: {text}; border: 1px solid {border}; border-radius: 4px; }}")
        self.title_label.setStyleSheet(f"color: {'#ffffff' if is_dark_theme else '#1f2328'};")
        self.sync_status_label.setStyleSheet(f"color: {'#8b949e' if is_dark_theme else '#57606a'};")
        self.summary_label.setStyleSheet(f"color: {'#8b949e' if is_dark_theme else '#57606a'};")
        for metric_name in ("CPU", "ASP"):
            section = getattr(self, f"{metric_name.lower()}_summary_card", None)
            if section is not None:
                section.set_theme(is_dark_theme)

    def load_month_options(self):
        months = set()
        for date_key in self.log_data_store.keys():
            if len(date_key) >= 7 and date_key[4] == "-":
                months.add(date_key[:7])
        if not months:
            months.add(datetime.now().strftime("%Y-%m"))
        options = sorted(months, reverse=True)
        self.month_combo.blockSignals(True)
        self.month_combo.clear()
        self.month_combo.addItems(options)
        self.month_combo.blockSignals(False)
        if self.month_combo.count() and self.month_combo.currentText() not in options:
            self.month_combo.setCurrentIndex(0)

    def refresh_report(self):
        if not self.isVisible():
            return
        month_key = self.month_combo.currentText() or datetime.now().strftime("%Y-%m")
        report = self._build_month_report(month_key, self.cpu_chart.mode)
        self._render_metric_panel(self.cpu_chart, self._summary_cards["CPU"], report, "CPU")
        report = self._build_month_report(month_key, self.asp_chart.mode)
        self._render_metric_panel(self.asp_chart, self._summary_cards["ASP"], report, "ASP")
        self.title_label.setText(f"IBM i Monthly ASP/CPU Report ({month_key})")

    def _render_metric_panel(self, chart_widget, summary_group, report, metric_name):
        rows = [row for row in report.get("rows", []) if row.get("metric") == metric_name]
        days = report.get("days", [])
        chart_widget.set_data(rows, days, report.get("month"))

        average_card = summary_group["average"]
        avg_value = round(sum(row.get("month_avg", 0.0) for row in rows) / len(rows), 2) if rows else 0.0
        average_card.value.setText(f"{avg_value:.2f}%")
        average_card.subtitle.setText(f"{len(rows)} server{'s' if len(rows) != 1 else ''} trend")

        server_list = summary_group["servers"]
        server_layout = QVBoxLayout()
        server_layout.setContentsMargins(0, 0, 0, 0)
        server_layout.setSpacing(6)
        server_layout = self._replace_layout(server_list, server_layout)

        ranking = sorted(rows, key=lambda row: row.get("month_avg", 0.0), reverse=True)
        for row in ranking:
            label = QLabel(f"{row.get('server', 'Unknown')}")
            label.setFont(self._make_font("Segoe UI", 8))
            label.setStyleSheet("color: #475569; background: transparent;")
            value = QLabel(f"{row.get('month_avg', 0.0):.2f}%")
            value.setFont(self._make_font("Segoe UI", 8, QFont.Weight.Bold))
            value.setStyleSheet("color: #1f2937; background: transparent;")
            row_widget = QWidget()
            row_widget.setFixedHeight(26)
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(8)
            dot = QLabel("●")
            dot.setStyleSheet("color: #3b82f6; font-size: 9px; background: transparent;")
            row_layout.addWidget(dot)
            row_layout.addWidget(label)
            row_layout.addStretch()
            row_layout.addWidget(value)
            server_layout.addWidget(row_widget)

    def _build_month_report(self, month_key, mode="month"):
        if len(month_key) != 7:
            return {"month": month_key, "days": [], "rows": []}

        try:
            year, month = map(int, month_key.split("-"))
        except ValueError:
            return {"month": month_key, "days": [], "rows": []}

        last_day = monthrange(year, month)[1]
        day_values = defaultdict(lambda: {"cpu": defaultdict(list), "asp": defaultdict(list)})

        for date_key, batches in self.log_data_store.items():
            if not date_key.startswith(f"{year:04d}-{month:02d}-"):
                continue
            day_num = int(date_key[-2:])
            for _, records in batches:
                for rec in records:
                    if not isinstance(rec, dict):
                        continue
                    server = self._normalize_server_name(
                        rec.get("host_name") or rec.get("server_name") or rec.get("lpar") or rec.get("server")
                    )
                    if not server:
                        continue
                    for metric_name in ("cpu", "asp"):
                        value = rec.get(metric_name)
                        if isinstance(value, (int, float)):
                            day_values[server][metric_name][day_num].append(float(value))

        rows = []
        for server in sorted(day_values.keys()):
            for metric_name, metric_label in (("cpu", "CPU"), ("asp", "ASP")):
                daily_map = {}
                for day_num in range(1, last_day + 1):
                    values = day_values.get(server, {}).get(metric_name, {}).get(day_num, [])
                    if values:
                        daily_map[day_num] = round(sum(values) / len(values), 2)
                if not daily_map:
                    continue
                if mode == "week":
                    bucket_map = defaultdict(list)
                    for day_num, value in daily_map.items():
                        bucket_map[(day_num - 1) // 7 + 1].append(value)
                    value_map = {
                        bucket: round(sum(values) / len(values), 2)
                        for bucket, values in bucket_map.items()
                    }
                elif mode == "month":
                    value_map = {1: round(sum(daily_map.values()) / len(daily_map), 2)}
                else:
                    value_map = daily_map
                month_avg = round(sum(value_map.values()) / len(value_map), 2)
                rows.append({
                    "server": server,
                    "metric": metric_label,
                    "day_map": value_map,
                    "month_avg": month_avg,
                })

        if mode == "week":
            periods = list(range(1, (last_day + 6) // 7 + 1))
        elif mode == "month":
            periods = [1]
        else:
            periods = list(range(1, last_day + 1))
        return {"month": month_key, "days": periods, "rows": rows}
