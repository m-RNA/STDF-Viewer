import os
from pathlib import Path
import unittest
from unittest.mock import patch
import math

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt5 import QtCore, QtGui, QtWidgets, QtTest
    from deps.SiteMap import SiteSummary, site_angle
    from deps.SiteMapWidget import SiteMapWidget
except ImportError:
    QtWidgets = None


@unittest.skipIf(QtWidgets is None, "Qt GUI dependencies unavailable")
class SiteMapWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        for font in (Path(__file__).resolve().parents[1] / "fonts").glob("*.ttf"):
            QtGui.QFontDatabase.addApplicationFont(str(font))
        cls.app.setFont(QtGui.QFont("LXGW WenKai Mono", 10))

    def setUp(self):
        self.widget = SiteMapWidget()
        self.widget.setAttribute(QtCore.Qt.WA_DontShowOnScreen, True)
        self.widget.resize(900, 650)
        self.widget.show()
        self.app.processEvents()

    def tearDown(self):
        self.widget.close()
        self.widget.deleteLater()
        self.app.processEvents()

    def test_64_points_render_and_labels_fit(self):
        rows = [SiteSummary(1, site, 100, 100 - site, site, 0, 0) for site in range(1, 65)]
        self.widget.setData(rows, [-1])
        self.app.processEvents()
        self.assertEqual(len(self.widget.sectors), 64)
        self.assertIn("Records: 6400", self.widget.summaryLabel.text())
        self.assertIn("Site 1", self.widget.tooltip(1))
        self.assertIn("Yield: 99.00%", self.widget.tooltip(1))
        for width, height in ((900, 650), (520, 570)):
            self.widget.resize(width, height)
            self.app.processEvents()
            image = self.widget.grab().toImage()
            output = Path("logs/site-map-qa")
            output.mkdir(parents=True, exist_ok=True)
            self.assertTrue(image.save(str(output / f"sites-{width}.png")))
            colors = [image.pixelColor(x, y) for x in range(0, image.width(), 4)
                      for y in range(100, image.height() - 30, 4)]
            self.assertGreater(sum(c.green() > c.red() * 1.3 and c.green() > c.blue() * 1.1
                                   or c.red() > c.green() * 1.3 and c.red() > c.blue() * 1.1
                                   for c in colors), 100)
            for index, sector in enumerate(self.widget.sectors):
                for other in self.widget.sectors[index + 1:]:
                    self.assertFalse(sector.shape().intersects(other.shape()))

    def test_all_pass_unknown_and_invalid_sites(self):
        rows = [SiteSummary(1, 1, 3, 3, 0, 0, 0), SiteSummary(1, 33, 2, 0, 0, 2, 0),
                SiteSummary(1, 255, 1, 0, 1, 0, 0)]
        self.widget.setData(rows, [-1])
        self.assertIn("255", self.widget.scaleLabel.text())
        self.assertIn("Yield: N/A", self.widget.tooltip(33))
        self.assertIn("No Data", self.widget.tooltip(2))
        for metric in range(3):
            self.widget.metricBox.setCurrentIndex(metric)
            self.assertEqual(len(self.widget.sectors), 64)

    def test_head_changes_and_selected_sites(self):
        rows = [SiteSummary(1, 1, 1, 1, 0, 0, 0), SiteSummary(2, 33, 10, 8, 2, 0, 0)]
        self.widget.setData(rows, [1, 33])
        self.widget.headBox.setCurrentIndex(1)
        self.assertEqual(self.widget.visibleRows()[0].head, 2)
        self.assertIn("Records: 10", self.widget.summaryLabel.text())
        self.assertEqual(len(self.widget.sectors), 2)
        self.widget.retranslate(True)
        self.assertIn("良率: 80.00%", self.widget.tooltip(33))
        self.widget.setData([], [])
        self.assertEqual(self.widget.sectors, [])
        self.assertFalse(self.widget.saveButton.isEnabled())

    def test_double_click_emits_head_and_site(self):
        self.widget.setData([SiteSummary(2, 33, 10, 8, 2, 0, 0)], [33])
        activated = []
        self.widget.siteActivated.connect(lambda head, site: activated.append((head, site)))

        self.widget.sectors[0].activated.emit(33)
        self.assertEqual(activated, [(2, 33)])

    def test_real_mouse_double_click_on_sector(self):
        self.widget.setData([SiteSummary(1, 1, 2, 1, 1, 0, 0)], [1])
        self.app.processEvents()
        activated = []
        self.widget.siteActivated.connect(lambda head, site: activated.append((head, site)))
        sector = self.widget.sectors[0]
        position = self.widget.plot.mapFromScene(self.widget.plot.plotItem.vb.mapViewToScene(
            QtCore.QPointF(*sector.labelPosition)))
        QtTest.QTest.mouseDClick(self.widget.plot.viewport(), QtCore.Qt.LeftButton, pos=position)
        self.app.processEvents()
        self.assertEqual(activated, [(1, 1)])

    def test_all_64_sector_mouse_hits_after_resize(self):
        self.widget.setData([SiteSummary(1, site, 2, 1, 1, 0, 0) for site in range(1, 65)], [-1])
        activated = []
        self.widget.siteActivated.connect(lambda head, site: activated.append((head, site)))
        viewport = self.widget.plot.viewport()
        for width, height in ((900, 650), (520, 570), (1200, 720)):
            self.widget.resize(width, height)
            self.app.processEvents()
            for sector in self.widget.sectors:
                radii = (43, 72, 101) if sector.site <= 32 else (119, 146, 173)
                for radius in radii:
                    with self.subTest(size=(width, height), site=sector.site, radius=radius):
                        angle = site_angle(sector.site)
                        point = QtCore.QPointF(-radius * math.sin(angle), -radius * math.cos(angle))
                        scene = self.widget.plot.plotItem.vb.mapViewToScene(point)
                        position = self.widget.plot.mapFromScene(scene)
                        move = QtGui.QMouseEvent(QtCore.QEvent.MouseMove, QtCore.QPointF(position),
                            QtCore.QPointF(viewport.mapToGlobal(position)), QtCore.Qt.NoButton,
                            QtCore.Qt.NoButton, QtCore.Qt.NoModifier)
                        QtWidgets.QApplication.sendEvent(viewport, move)
                        hovered = [item.site for item in self.widget.sectors if item.hovered]
                        self.assertEqual(hovered, [sector.site])
                        QtTest.QTest.mouseClick(viewport, QtCore.Qt.LeftButton, pos=position)
                        activated.clear()
                        QtTest.QTest.mouseDClick(viewport, QtCore.Qt.LeftButton, pos=position)
                        QtTest.QTest.mouseRelease(viewport, QtCore.Qt.LeftButton, pos=position)
                        self.app.processEvents()
                        self.assertEqual(activated, [(1, sector.site)])

    def test_sector_contains_only_its_painted_path(self):
        self.widget.setData([SiteSummary(1, site, 1, 1, 0, 0, 0) for site in range(1, 65)], [-1])
        for expected in self.widget.sectors:
            point = QtCore.QPointF(*expected.labelPosition)
            matching = [sector.site for sector in self.widget.sectors if sector.contains(point)]
            self.assertEqual(matching, [expected.site])

    def test_tooltip_on_labels_matches_sector(self):
        self.widget.setData([SiteSummary(1, site, 2, 1, 1, 0, 0) for site in range(1, 65)], [-1])
        self.app.processEvents()
        viewport = self.widget.plot.viewport()
        for site in (1, 2, 4, 16, 32, 33, 34, 48, 64):
            sector = self.widget.sectors[site - 1]
            scene = self.widget.plot.plotItem.vb.mapViewToScene(QtCore.QPointF(*sector.labelPosition))
            position = self.widget.plot.mapFromScene(scene)
            event = QtGui.QHelpEvent(QtCore.QEvent.ToolTip, position, viewport.mapToGlobal(position))
            QtWidgets.QApplication.sendEvent(viewport, event)
            self.app.processEvents()
            self.assertEqual(QtWidgets.QToolTip.text(), self.widget.tooltip(site))
        QtWidgets.QToolTip.hideText()

    def test_hole_ring_gap_and_outside_do_not_activate_sectors(self):
        self.widget.setData([SiteSummary(1, site, 2, 1, 1, 0, 0) for site in range(1, 65)], [-1])
        self.app.processEvents()
        activated = []
        self.widget.siteActivated.connect(lambda head, site: activated.append((head, site)))
        for radius in (0, 20, 110, 186):
            angle = site_angle(1)
            point = QtCore.QPointF(-radius * math.sin(angle), -radius * math.cos(angle))
            scene = self.widget.plot.plotItem.vb.mapViewToScene(point)
            position = self.widget.plot.mapFromScene(scene)
            viewport = self.widget.plot.viewport()
            QtTest.QTest.mouseClick(viewport, QtCore.Qt.LeftButton, pos=position)
            QtTest.QTest.mouseDClick(viewport, QtCore.Qt.LeftButton, pos=position)
            QtTest.QTest.mouseRelease(viewport, QtCore.Qt.LeftButton, pos=position)
            self.app.processEvents()
        self.assertEqual(activated, [])

    def test_center_crosshairs_do_not_intercept_mouse(self):
        self.widget.setData([SiteSummary(1, 1, 2, 1, 1, 0, 0)], [-1])
        self.assertEqual(len(self.widget.crosshairs), 2)
        self.assertEqual({line.angle for line in self.widget.crosshairs}, {0, 90})
        for line in self.widget.crosshairs:
            self.assertEqual(line.value(), 0)
            self.assertEqual(line.acceptedMouseButtons(), QtCore.Qt.NoButton)
            self.assertFalse(line.acceptHoverEvents())
        self.widget.setData([], [])
        self.assertEqual(self.widget.crosshairs, [])

    def test_export_image(self):
        self.widget.setData([SiteSummary(1, site, 1, 1, 0, 0, 0) for site in range(1, 65)], [-1])
        output = Path("logs/site-map-qa/export.png")
        output.parent.mkdir(parents=True, exist_ok=True)
        with patch.object(QtWidgets.QFileDialog, "getSaveFileName", return_value=(str(output), "PNG (*.png)")):
            self.widget.saveImage()
        image = QtGui.QImage(str(output))
        self.assertFalse(image.isNull())
        self.assertEqual(image.width(), 1200)


if __name__ == "__main__":
    unittest.main()
