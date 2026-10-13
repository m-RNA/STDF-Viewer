"""The site view must work in the real window without wafer records."""
import importlib.util
import atexit
import os
from pathlib import Path
import struct
import sys
import tempfile
import time
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

try:
    import rust_stdf_helper
    from PyQt5 import QtWidgets
except ImportError:
    rust_stdf_helper = QtWidgets = None

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipIf(rust_stdf_helper is None or QtWidgets is None, 'GUI/Rust dependencies unavailable')
class SiteMapWindowTests(unittest.TestCase):
    def test_real_stdf_load_tab_filters_and_stream_drilldown(self):
        spec = importlib.util.spec_from_file_location('site_map_test_viewer', ROOT / 'STDF-Viewer.py')
        viewer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(viewer)
        app = QtWidgets.QApplication.instance() or viewer.StdfApplication([])
        old_appdata, old_config, old_hook = sys.appDataFolder, sys.CONFIG_PATH, sys.excepthook
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'logs').mkdir()
            sys.appDataFolder = folder
            sys.CONFIG_PATH = str(Path(folder) / 'viewer.config')
            window = viewer.MyWindow()
            failures = []
            window.signals.statusSignal.connect(lambda message, *_args: failures.append(message))

            def record(typ, sub, body):
                return struct.pack('<HBB', len(body), typ, sub) + body

            def cn(value):
                encoded = value.encode('ascii')
                return bytes([len(encoded)]) + encoded

            stamp = 1791734400
            mir = struct.pack('<IIBcccHc', stamp, stamp, 0, b'P', b' ', b' ', 0, b' ')
            mir += cn('SITE-QA') + cn('SAMPLE') + b'\0' * 28
            data = record(0, 10, b'\2\4') + record(1, 10, mir)
            data += record(1, 80, b'\1\1\2\1\41' + b'\0' * 16)
            for site, flag in ((1, 0), (1, 8), (33, 0)):
                data += record(5, 10, bytes([1, site]))
                data += record(5, 20, struct.pack('<BBBHHHhhI', 1, site, flag, 0,
                    2 if flag else 1, 2 if flag else 1, -32768, -32768, 0) + cn('SAME-PART'))
            data += record(1, 30, struct.pack('<BBIIIII', 255, 0, 3, 0, 0, 2, 3))
            data += record(1, 20, struct.pack('<I', stamp))
            source = Path(folder) / 'stream.stdf'
            source.write_bytes(data)
            try:
                window.openNewFile([str(source)])
                deadline = time.monotonic() + 30
                while (window._fileLoading or window.data_interface is None) and time.monotonic() < deadline:
                    app.processEvents()
                    time.sleep(.01)
                self.assertIsNotNone(window.data_interface, failures)
                self.assertFalse(window._fileLoading, failures)
                self.assertFalse(window.ui.tabControl.isTabEnabled(viewer.tab.Wafer))
                self.assertTrue(window.ui.tabControl.isTabEnabled(viewer.tab.SiteMap))
                window.ui.tabControl.setCurrentIndex(viewer.tab.SiteMap)
                app.processEvents()
                rows = window.siteMap.visibleRows()
                self.assertEqual([(r.site, r.records, r.failed) for r in rows], [(1, 2, 1), (33, 1, 0)])
                self.assertEqual(window.ui.dataTable.model().rowCount(), 2)
                self.assertEqual(rows[0].yield_percent, 50)
                selected = []
                window.showDutDataTable = lambda indices: selected.extend(indices)
                window.siteMap.onSectorActivated(1)
                self.assertEqual(selected, [(0, 1), (0, 2)])
                window.ui.All.setChecked(False)
                window.site_cb_dict[1].setChecked(True)
                window.onSelect()
                app.processEvents()
                self.assertEqual([r.site for r in window.siteMap.visibleRows()], [1])
                window.onLoadState(True)
                self.assertFalse(window.ui.tabControl.isTabEnabled(viewer.tab.SiteMap))
                window.onLoadState(False)
                self.assertTrue(window.ui.tabControl.isTabEnabled(viewer.tab.SiteMap))
            finally:
                window.onExit()
                atexit.unregister(window.onExit)
                window.close()
                app.processEvents()
                sys.appDataFolder, sys.CONFIG_PATH, sys.excepthook = old_appdata, old_config, old_hook


if __name__ == '__main__':
    unittest.main()
