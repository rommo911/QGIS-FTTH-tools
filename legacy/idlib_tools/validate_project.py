r"""
Headless load of the QGIS project; reports any layer that fails to resolve.

Run with QGIS's bundled interpreter so PyQGIS is importable:

    "C:\Program Files\QGIS 4.2.1\bin\python-qgis.bat" tools\validate_project.py

Exit code is 0 only when every layer is valid.
"""
from __future__ import annotations

import glob
import os
import sys

from qgis.core import QgsApplication, QgsProject

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 else None
    if not target:
        found = sorted(glob.glob(os.path.join(ROOT, "*.qgz")))
        if not found:
            print("no .qgz found")
            return 2
        target = found[0]

    QgsApplication.setPrefixPath(os.environ.get("QGIS_PREFIX_PATH", ""), True)
    app = QgsApplication([], False)
    app.initQgis()

    project = QgsProject.instance()
    if not project.read(target):
        print(f"FAILED to read project: {target}")
        app.exitQgis()
        return 2

    layers = project.mapLayers()
    bad = [(lid, l) for lid, l in layers.items() if not l.isValid()]

    print(f"project        : {os.path.basename(target)}")
    print(f"layers loaded  : {len(layers)}")
    print(f"invalid layers : {len(bad)}")
    for lid, l in bad:
        print(f"    ! {l.name()!r}  id={lid}  source={l.source()}")

    if not bad:
        total = 0
        for l in layers.values():
            try:
                total += l.featureCount()
            except Exception:
                pass
        print(f"total features : {total}")

    app.exitQgis()
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
