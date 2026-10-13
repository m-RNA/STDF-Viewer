"""Site layout and raw-stream aggregation, independent of wafer coordinates."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class SiteSummary:
    head: int
    site: int
    records: int
    passed: int
    failed: int
    unknown: int
    superseded: int

    @property
    def yield_percent(self):
        known = self.passed + self.failed
        return 100.0 * self.passed / known if known else None

    @property
    def failure_percent(self):
        value = self.yield_percent
        return 100.0 - value if value is not None else None


def site_angle(site):
    """The gap before Site 1/33 is at six o'clock; numbering is clockwise."""
    if not isinstance(site, int) or not 1 <= site <= 64:
        raise ValueError("Two-ring layout requires Site 1..64")
    return ((site - 1) % 32 + .5) * math.tau / 32


def site_position(site):
    angle = site_angle(site)
    radius = 100 if site <= 32 else 200
    return round(-radius * math.sin(angle)), round(-radius * math.cos(angle))


def summarize_sites(rows, heads, sites, files):
    heads, sites, files = set(heads), set(sites), set(files)
    if not heads or not sites or not files:
        return []
    selected = {}
    for fid, head, site, *counts in rows:
        if fid not in files or head not in heads or (site not in sites and -1 not in sites):
            continue
        values = selected.setdefault((head, site), [0] * 5)
        for index, count in enumerate(counts):
            values[index] += count
    return [SiteSummary(head, site, *counts) for (head, site), counts in sorted(selected.items())]
