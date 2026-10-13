"""Two-ring site summary, with no WIR/WRR or XY dependency."""
from pathlib import Path
import math

import numpy as np
import pyqtgraph as pg
from pyqtgraph.exporters import ImageExporter
from PyQt5 import QtCore, QtGui, QtWidgets

from deps.SiteMap import site_angle

TEXT = {
    "Site Map": "工位位置图", "Failure Rate (%)": "失败率 (%)",
    "Failure Count": "FAIL 次数", "Test Count": "测试次数",
    "Head": "测试头", "Site": "工位", "Records": "测试次数", "PASS": "PASS 次数",
    "FAIL": "FAIL 次数", "Unknown": "未知结果", "Superseded": "已被替代",
    "Yield": "良率", "No Data": "无数据", "No Selection": "未选择文件、测试头或工位",
    "Unmapped Sites": "未映射工位", "Save Image": "保存图片",
    "Image Saved": "图片已保存", "Save Failed": "保存失败",
}


class SiteSector(pg.GraphicsObject):
    activated = QtCore.pyqtSignal(int)

    def __init__(self, site, color, tooltip):
        super().__init__()
        self.site = site
        self.color = color
        self.hovered = False
        inner, outer = (36, 108) if site <= 32 else (112, 180)
        center = site_angle(site)
        half = math.pi / 32 - math.radians(.35)
        angles = np.linspace(center - half, center + half, 9)
        points = [QtCore.QPointF(-outer * math.sin(a), -outer * math.cos(a)) for a in angles]
        points += [QtCore.QPointF(-inner * math.sin(a), -inner * math.cos(a)) for a in angles[::-1]]
        self.path = QtGui.QPainterPath(points[0])
        for point in points[1:]:
            self.path.lineTo(point)
        self.path.closeSubpath()
        # The ViewBox clips its children; include our own shape in Qt's native hit-test clip path.
        self.setFlag(QtWidgets.QGraphicsItem.ItemClipsToShape, True)
        radius = (inner + outer) / 2
        self.labelPosition = (-radius * math.sin(center), -radius * math.cos(center))
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(QtCore.Qt.LeftButton)
        self.setToolTip(tooltip)

    def boundingRect(self):
        return self.path.boundingRect().adjusted(-2, -2, 2, 2)

    def shape(self):
        return self.path

    def paint(self, painter, _option, _widget):
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setBrush(self.color)
        painter.setPen(pg.mkPen("#17212b" if self.hovered else "#ffffff", width=2 if self.hovered else 1))
        painter.drawPath(self.path)

    def hoverEnterEvent(self, event):
        self.hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        event.accept()

    def mouseDoubleClickEvent(self, event):
        self.activated.emit(self.site)
        event.accept()


class SiteMapWidget(QtWidgets.QWidget):
    siteActivated = QtCore.pyqtSignal(int, int)
    headChanged = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.summaries = []
        self.selectedSites = []
        self.chinese = False
        self.setObjectName("siteMapPanel")
        layout = QtWidgets.QVBoxLayout(self)
        controls = QtWidgets.QHBoxLayout()
        self.headLabel = QtWidgets.QLabel()
        self.headBox = QtWidgets.QComboBox()
        self.headBox.setObjectName("siteMapHead")
        self.metricBox = QtWidgets.QComboBox()
        self.metricBox.setObjectName("siteMapMetric")
        self.metricBox.addItems(["", "", ""])
        self.metricBox.setMinimumWidth(160)
        self.saveButton = QtWidgets.QToolButton()
        self.saveButton.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogSaveButton))
        controls.addWidget(self.headLabel)
        controls.addWidget(self.headBox)
        controls.addSpacing(12)
        controls.addWidget(self.metricBox)
        controls.addStretch()
        controls.addWidget(self.saveButton)
        layout.addLayout(controls)
        self.summaryLabel = QtWidgets.QLabel()
        self.summaryLabel.setWordWrap(True)
        self.summaryLabel.setObjectName("siteMapSummary")
        layout.addWidget(self.summaryLabel)
        self.plot = pg.PlotWidget(background="w")
        self.plot.setObjectName("siteMapPlot")
        self.plot.setMinimumHeight(340)
        self.plot.setAspectLocked(True)
        self.plot.setMenuEnabled(False)
        self.plot.hideAxis("left")
        self.plot.hideAxis("bottom")
        self.plot.setMouseEnabled(x=False, y=False)
        layout.addWidget(self.plot, 1)
        self.scaleLabel = QtWidgets.QLabel()
        self.scaleLabel.setWordWrap(True)
        layout.addWidget(self.scaleLabel)
        self.metricBox.currentIndexChanged.connect(self.redraw)
        self.headBox.currentIndexChanged.connect(self.onHeadChanged)
        self.saveButton.clicked.connect(self.saveImage)
        self.retranslate(False)

    def text(self, value):
        return TEXT.get(value, value) if self.chinese else value

    def retranslate(self, chinese):
        self.chinese = chinese
        self.headLabel.setText(self.text("Head"))
        with QtCore.QSignalBlocker(self.metricBox):
            for index, name in enumerate(("Failure Rate (%)", "Failure Count", "Test Count")):
                self.metricBox.setItemText(index, self.text(name))
        self.saveButton.setToolTip(self.text("Save Image"))
        self.redraw()

    def setData(self, summaries, selectedSites):
        self.summaries = summaries
        self.selectedSites = list(selectedSites)
        previous = self.headBox.currentData()
        heads = sorted({row.head for row in summaries})
        with QtCore.QSignalBlocker(self.headBox):
            self.headBox.clear()
            for head in heads:
                self.headBox.addItem(str(head), head)
            self.headBox.setCurrentIndex(heads.index(previous) if previous in heads else (0 if heads else -1))
        self.redraw()

    def visibleRows(self):
        return [row for row in self.summaries if row.head == self.headBox.currentData()]

    def onHeadChanged(self):
        self.redraw()
        self.headChanged.emit()

    def tooltip(self, site):
        row = next((r for r in self.visibleRows() if r.site == site), None)
        lines = [f"{self.text('Head')} {self.headBox.currentData()} / Site {site}"]
        if row is None:
            return "\n".join(lines + [self.text("No Data")])
        for name, value in (("Records", row.records), ("PASS", row.passed), ("FAIL", row.failed),
                            ("Unknown", row.unknown), ("Superseded", row.superseded)):
            lines.append(f"{self.text(name)}: {value}")
        value = row.yield_percent
        lines.append(f"{self.text('Yield')}: {value:.2f}%" if value is not None else f"{self.text('Yield')}: N/A")
        return "\n".join(lines)

    def redraw(self, *_args):
        self.plot.clear()
        self.crosshairs = []
        self.saveButton.setEnabled(bool(self.summaries))
        rows = self.visibleRows()
        if not rows:
            self.summaryLabel.setText(self.text("No Selection"))
            self.scaleLabel.clear()
            self.sectors = []
            return
        by_site = {row.site: row for row in rows}
        total, passed, failed, unknown = (sum(getattr(row, field) for row in rows)
                                           for field in ("records", "passed", "failed", "unknown"))
        self.summaryLabel.setText("   |   ".join(f"{self.text(name)}: {count}" for name, count in
                                               (("Records", total), ("PASS", passed), ("FAIL", failed), ("Unknown", unknown))))
        metric = self.metricBox.currentIndex()
        maximum = 100 if metric == 0 else max((r.failed if metric == 1 else r.records for r in rows), default=0)
        maximum = max(1, maximum)
        color_map = pg.ColorMap([0, .5, 1], ["#249e59", "#f5c04a", "#ce383f"])
        self.sectors = []
        shown = set(range(1, 65)) if -1 in self.selectedSites else set(self.selectedSites)
        for site in sorted(shown & set(range(1, 65))):
            row = by_site.get(site)
            value = None if row is None else (row.failure_percent if metric == 0 else row.failed if metric == 1 else row.records)
            color = color_map.mapToQColor(value / maximum) if value is not None else QtGui.QColor("#e0e3e7")
            sector = SiteSector(site, color, self.tooltip(site))
            sector.activated.connect(self.onSectorActivated)
            self.plot.addItem(sector)
            self.sectors.append(sector)
            label = pg.TextItem(str(site), color="#17212b", anchor=(.5, .5))
            font = QtGui.QFont(self.font())
            font.setPointSize(8)
            label.setFont(font)
            label.setPos(*sector.labelPosition)
            label.setAcceptedMouseButtons(QtCore.Qt.NoButton)
            label.setParentItem(sector)
        for angle in (0, 90):
            reference = pg.InfiniteLine(pos=0, angle=angle, movable=False,
                                       pen=pg.mkPen("#8b949e", width=1, style=QtCore.Qt.DashLine))
            reference.setAcceptedMouseButtons(QtCore.Qt.NoButton)
            reference.setAcceptHoverEvents(False)
            reference.setZValue(2)
            self.plot.addItem(reference)
            self.crosshairs.append(reference)
        self.plot.setRange(xRange=(-190, 190), yRange=(-190, 190), padding=0)
        caption = (f"0% → 100%   |   {self.text('Yield')} = PASS / (PASS + FAIL)" if metric == 0
                   else f"0 → {maximum}   |   {self.metricBox.currentText()}")
        unmapped = sorted(site for site in by_site if not 1 <= site <= 64)
        if unmapped:
            caption += "   |   " + self.text("Unmapped Sites") + ": " + ", ".join(map(str, unmapped))
        self.scaleLabel.setText(caption)

    def onSectorActivated(self, site):
        if any(row.site == site for row in self.visibleRows()):
            self.siteActivated.emit(self.headBox.currentData(), site)

    def saveImage(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, self.text("Save Image"), "site-map.png", "PNG (*.png)")
        if path:
            try:
                if Path(path).suffix.lower() != ".png":
                    path += ".png"
                exporter = ImageExporter(self.plot.plotItem)
                exporter.parameters()["width"] = 1200
                exporter.export(path)
            except Exception as error:
                QtWidgets.QMessageBox.warning(self, self.text("Save Failed"), str(error))
