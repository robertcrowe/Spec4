"""``spec4.app`` imports, in a fresh interpreter, the way the server starts.

The import ordering in ``app.py`` is load-bearing (D-LR1, cleanup Rule 5):
the litellm log level and ``suppress_debug_info`` must be set before litellm
is first imported, and the callback modules must be imported after ``app``
exists. Every other test in the suite imports ``spec4.app`` into a process
where some of those modules are already loaded, so none of them can see a
reordering — the first import wins and the rest are cache hits.

This test spawns a subprocess whose *first* import is ``spec4.app`` and
reports what it finds as one JSON line. It also runs the ``--version`` path
of ``main()``, the only branch of the entry point that does not start a
server. Nothing here needs a browser or the network.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

_PROBE = r"""
import io, json, os, sys
from contextlib import redirect_stdout

assert "litellm" not in sys.modules, "probe must import spec4.app first"
import spec4.app as app_module
import litellm
from dash._callback import GLOBAL_CALLBACK_MAP
import dash_mantine_components as dmc
from spec4 import __version__

layout = app_module.app.layout
page = None
stack = [layout]
while stack:
    node = stack.pop()
    if getattr(node, "id", None) == "page-content":
        page = node
        break
    children = getattr(node, "children", None)
    if children is None:
        continue
    stack.extend(children if isinstance(children, (list, tuple)) else [children])

buf = io.StringIO()
sys.argv = ["spec4", "--version"]
try:
    with redirect_stdout(buf):
        app_module.main()
except SystemExit as exc:
    version_exit = exc.code
else:
    version_exit = "no exit"

print(json.dumps({
    "litellm_log": os.environ.get("LITELLM_LOG"),
    "suppress_debug_info": litellm.suppress_debug_info,
    "callbacks_imported": (
        "spec4.callbacks" in sys.modules and "spec4.callbacks.designer" in sys.modules
    ),
    "callback_count": len(GLOBAL_CALLBACK_MAP),
    "has_render_page": any(
        key.lstrip(".").startswith("page-content.children")
        for key in GLOBAL_CALLBACK_MAP
    ),
    "layout_is_mantine_provider": isinstance(layout, dmc.MantineProvider),
    "page_slot_found": page is not None,
    "page_slot_disables_clicks": getattr(page, "disable_n_clicks", None),
    "version_output": buf.getvalue(),
    "version_exit": version_exit,
    "version": __version__,
}))
"""


def _run_probe() -> tuple[dict[str, object], str]:
    env = {
        k: v for k, v in os.environ.items() if k not in ("DASH_DEBUG", "LITELLM_LOG")
    }
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Traceback" not in proc.stderr, proc.stderr
    line = proc.stdout.strip().splitlines()[-1]
    return json.loads(line), proc.stderr


class TestAppImportsCleanly:
    def test_the_app_constructs_and_registers_everything(self) -> None:
        report, _ = _run_probe()
        assert report["litellm_log"] == "ERROR"
        assert report["suppress_debug_info"] is True
        assert report["callbacks_imported"] is True
        assert isinstance(report["callback_count"], int)
        assert report["callback_count"] > 0
        assert report["has_render_page"] is True
        assert report["layout_is_mantine_provider"] is True
        assert report["page_slot_found"] is True
        assert report["page_slot_disables_clicks"] is True

    def test_version_flag_prints_and_exits_zero(self) -> None:
        report, _ = _run_probe()
        assert report["version_exit"] == 0
        assert report["version_output"] == f"spec4 {report['version']}\n"
