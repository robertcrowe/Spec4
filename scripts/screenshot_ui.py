"""Take screenshots of the Spec4 UI showing Agentifier integration."""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("working-notes")
out_dir.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)

    # 1. Landing page
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto("http://localhost:8050/", wait_until="networkidle", timeout=15000)
    page.screenshot(path=str(out_dir / "01-landing.png"), full_page=False)
    print("01-landing.png saved")

    # 2. Direct to /agents URL (the agent select page, which shows the pipeline)
    page2 = browser.new_page(viewport={"width": 1280, "height": 900})
    page2.goto("http://localhost:8050/agents", wait_until="networkidle", timeout=15000)
    page2.screenshot(path=str(out_dir / "02-agents.png"), full_page=True)
    print("02-agents.png saved")

    browser.close()
