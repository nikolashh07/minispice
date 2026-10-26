"""Turn coverage.py's JSON report into a shields.io badge description.

    coverage run -m pytest && coverage json && python tools/coverage_badge.py coverage.json site/coverage.json

The README's badge reads that file from the GitHub Pages site, so it updates on every push.
"""

import json
import sys


def badge(percent):
    color = "brightgreen" if percent >= 90 else "green" if percent >= 80 else "yellow" if percent >= 70 else "red"
    return {"schemaVersion": 1, "label": "coverage", "message": f"{percent:.0f}%", "color": color}


def main(report_path, out_path):
    with open(report_path, encoding="utf-8") as handle:
        percent = json.load(handle)["totals"]["percent_covered"]
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(badge(percent), handle)
    print(f"coverage {percent:.1f}% -> {out_path}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
