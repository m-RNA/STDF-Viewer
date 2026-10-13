"""Exercise the compiled fetcher against a small session database."""
from contextlib import closing
from pathlib import Path
import re
import sqlite3
import struct
import tempfile
import unittest

try:
    import rust_stdf_helper
except ImportError:
    rust_stdf_helper = None

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipIf(rust_stdf_helper is None, "Rust extension unavailable")
class SiteMapIntegrationTests(unittest.TestCase):
    def test_rust_fetcher_stream_counts_and_drilldown(self):
        self.assertTrue(hasattr(rust_stdf_helper.DataFetcher, "get_site_summary_rows"),
                        "Rebuild the Rust helper to include the site-summary API")
        with (ROOT / "deps/rust_stdf_helper/src/database/schema.rs").open(encoding="utf-8") as handle:
            schema = re.search(r'CREATE_TABLE_SQL: &str = "(.*?)";', handle.read(), re.S).group(1)
        with tempfile.TemporaryDirectory() as folder:
            database = str(Path(folder) / "session.db")
            with closing(sqlite3.connect(database)) as conn:
                conn.executescript(schema)
                conn.execute("INSERT INTO File_List (Fid,SubFid,Filename) VALUES (0,0,'sample.stdf')")
                conn.execute("INSERT INTO File_Info VALUES (0,0,'BYTE_ORD','Little endian')")
                conn.executemany("INSERT INTO Dut_Info (Fid,HEAD_NUM,SITE_NUM,DUTIndex,Flag,Supersede,PartID) "
                                 "VALUES (?,?,?,?,?,?,?)", [
                    (0, 1, 1, 1, 0, 1, 'retested'), (0, 1, 1, 2, 8, 0, 'retested'),
                    (0, 2, 1, 3, 16, 0, 'unknown'), (0, 1, 33, 4, None, 0, 'incomplete'),
                ])
                conn.commit()
            fetcher = rust_stdf_helper.DataFetcher(database)
            try:
                self.assertEqual(fetcher.get_wafer_count(), [0])
                self.assertEqual(fetcher.get_site_summary_rows(), [
                    (0, 1, 1, 2, 1, 1, 0, 1), (0, 1, 33, 1, 0, 0, 1, 0), (0, 2, 1, 1, 0, 0, 1, 0),
                ])
                indices = fetcher.get_dut_index_dict_by_head_site([1], [1], [0])
                self.assertEqual(list(indices[0]), [1, 2])
            finally:
                fetcher.close()
                del fetcher

    def test_real_wafer_records_still_group_and_keep_xy(self):
        def cn(text):
            encoded = text.encode('ascii')
            return bytes([len(encoded)]) + encoded

        def rec(typ, sub, payload):
            return struct.pack('<HBB', len(payload), typ, sub) + payload

        stamp = 1791734400
        mir = struct.pack('<IIBcccHc', stamp, stamp, 0, b'P', b' ', b' ', 0, b' ')
        mir += cn('QA-LOT') + cn('QA-PART') + b'\0' * 28
        data = rec(0, 10, b'\2\4') + rec(1, 10, mir)
        data += rec(1, 80, b'\1\1\1\1' + b'\0' * 16)
        data += rec(2, 10, struct.pack('<BBI', 1, 1, stamp) + cn('QA-WAFER'))
        data += rec(5, 10, b'\1\1')
        data += rec(5, 20, struct.pack('<BBBHHHhhI', 1, 1, 0, 0, 1, 1, 5, 7, 0) + cn('QA-DUT'))
        data += rec(2, 20, struct.pack('<BBIIIIII', 1, 1, stamp, 1, 0, 0, 1, 1) + cn('QA-WAFER') + b'\0' * 5)
        data += rec(1, 30, struct.pack('<BBIIIII', 255, 0, 1, 0, 0, 1, 1))
        data += rec(1, 20, struct.pack('<I', stamp))

        class Progress:
            def emit(self, value):
                pass

        class Stop:
            stop = False

        with tempfile.TemporaryDirectory() as folder:
            source, database = Path(folder) / 'wafer.stdf', Path(folder) / 'wafer.db'
            source.write_bytes(data)
            rust_stdf_helper.generate_database(str(database), [[str(source)]],
                rust_stdf_helper.TestIDType.TestNumberAndName, Progress(), Stop())
            fetcher = rust_stdf_helper.DataFetcher(str(database))
            try:
                self.assertEqual(fetcher.get_wafer_count(), [1])
                self.assertIn('QA-WAFER', fetcher.get_wafer_list()[1])
                self.assertEqual(fetcher.get_wafer_bounds(1, 0), (5, 5, 7, 7))
                self.assertEqual(fetcher.get_site_summary_rows(), [(0, 1, 1, 1, 1, 0, 0, 0)])
            finally:
                fetcher.close()
                del fetcher


if __name__ == '__main__':
    unittest.main()
