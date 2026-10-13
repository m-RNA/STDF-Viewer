"""Raw-stream site summaries must not behave like unique-die wafer maps."""
import math
from contextlib import closing
from pathlib import Path
import re
import sqlite3
import unittest

from deps.SiteMap import SiteSummary, site_position, summarize_sites

ROOT = Path(__file__).resolve().parents[1]


def site_query():
    with (ROOT / "deps/rust_stdf_helper/src/database/schema.rs").open(encoding="utf-8") as handle:
        source = handle.read()
    match = re.search(r'FETCH_SELECT_SITE_SUMMARY: &str = "(.*?)";', source, re.S)
    if match is None:
        raise AssertionError("site summary SQL not found")
    return match.group(1)


class SiteSummaryTests(unittest.TestCase):
    def test_64_positions_are_unique_with_gap_at_six_oclock(self):
        positions = [site_position(site) for site in range(1, 65)]
        self.assertEqual(len(set(positions)), 64)
        for start, radius in ((1, 100), (33, 200)):
            before = site_position(start + 31)
            after = site_position(start)
            self.assertEqual(before[0], -after[0])
            self.assertEqual(before[1], after[1])
            self.assertGreater(before[0], 0)
            self.assertLess(after[0], 0)
            self.assertLess(after[1], -radius * .99)
            for offset in range(32):
                x, y = site_position(start + offset)
                self.assertLess(abs(math.hypot(x, y) - radius), 1)
            self.assertLess(site_position(start + 1)[0], 0)

    def test_invalid_site_is_not_silently_remapped(self):
        for site in (0, 65, 255, -1, None, "1"):
            with self.subTest(site=site), self.assertRaises(ValueError):
                site_position(site)

    def test_sql_counts_retests_superseded_and_unknown(self):
        with closing(sqlite3.connect(":memory:")) as conn:
            conn.execute("CREATE TABLE Dut_Info (Fid, HEAD_NUM, SITE_NUM, Flag, Supersede, PartID)")
            conn.executemany("INSERT INTO Dut_Info VALUES (?,?,?,?,?,?)", [
                (0, 1, 1, 0, 1, "same-part"),
                (0, 1, 1, 8, 0, "same-part"),
                (0, 1, 1, 16, 0, "unknown"),
                (0, 1, 1, 24, 0, "unknown"),
                (0, 1, 1, None, 0, "incomplete"),
                (0, 2, 1, 0, 0, "head2"),
                (1, 1, 1, 0, 0, "file2"),
                (1, 1, 255, 0, 0, "invalid-site"),
            ])
            rows = list(conn.execute(site_query()))
        self.assertEqual(rows[0], (0, 1, 1, 5, 1, 1, 3, 1))
        self.assertEqual(rows[1], (0, 2, 1, 1, 1, 0, 0, 0))
        all_rows = summarize_sites(rows, [1, 2], [-1], [0, 1])
        self.assertEqual(all_rows[0], SiteSummary(1, 1, 6, 2, 1, 3, 1))
        self.assertEqual([row.site for row in all_rows], [1, 255, 1])
        self.assertAlmostEqual(all_rows[0].yield_percent, 200 / 3)

    def test_files_heads_and_sites_are_independent(self):
        rows = [(0, 1, 1, 2, 1, 1, 0, 0), (1, 1, 1, 3, 3, 0, 0, 1),
                (0, 2, 1, 5, 4, 1, 0, 0), (0, 1, 33, 1, 0, 0, 1, 0)]
        result = summarize_sites(rows, [1], [1], [0])
        self.assertEqual(result, [SiteSummary(1, 1, 2, 1, 1, 0, 0)])
        result = summarize_sites(rows, [1], [-1], [0, 1])
        self.assertEqual(result[0].records, 5)
        self.assertEqual(result[1].site, 33)
        for heads, sites, files in (([], [-1], [0]), ([1], [], [0]), ([1], [-1], [])):
            self.assertEqual(summarize_sites(rows, heads, sites, files), [])

    def test_all_pass_and_unknown_do_not_divide_by_zero(self):
        self.assertEqual(SiteSummary(1, 1, 3, 3, 0, 0, 0).failure_percent, 0)
        self.assertIsNone(SiteSummary(1, 1, 3, 0, 0, 3, 0).yield_percent)


if __name__ == "__main__":
    unittest.main()
