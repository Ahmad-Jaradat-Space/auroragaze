"""Capture screenshots of the live AuroraGaze demo for the README.

Usage: python _capture.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

URL = "https://auroragaze.fly.dev"
OUT = Path(__file__).resolve().parent / "docs" / "img"


async def capture() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        ctx = await browser.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=2)
        page = await ctx.new_page()

        print("warming server…")
        # auto-stop machine — first hit can take ~15s
        await page.goto(URL, wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(15_000)
        print("loading hero…")
        await page.goto(URL, wait_until="networkidle", timeout=60_000)
        await page.wait_for_timeout(3000)
        await page.screenshot(path=str(OUT / "hero.png"), full_page=False)

        print("clicking Get briefing for aurora…")
        await page.click("#brief-aurora")
        # wait for trace lines, then for briefing
        await page.wait_for_function(
            "document.querySelectorAll('#trace .step').length >= 3",
            timeout=120_000,
        )
        await page.screenshot(path=str(OUT / "agent-trace.png"), clip={"x": 0, "y": 600, "width": 1280, "height": 320})
        await page.wait_for_selector(".briefing", timeout=60_000)
        await page.wait_for_timeout(800)
        # full-page after briefing settles
        await page.screenshot(path=str(OUT / "aurora-full.png"), full_page=True)
        # briefing card close-up
        elem = await page.query_selector(".briefing")
        if elem:
            await elem.screenshot(path=str(OUT / "aurora-card.png"))

        print("switching to satellite persona…")
        await page.click("button[data-mode='satellite']")
        await page.wait_for_timeout(400)
        await page.click("#brief-satellite")
        await page.wait_for_selector(".briefing", timeout=60_000)
        await page.wait_for_timeout(800)
        elem = await page.query_selector(".briefing")
        if elem:
            await elem.screenshot(path=str(OUT / "satellite-card.png"))
        await page.screenshot(path=str(OUT / "satellite-full.png"), full_page=True)

        # imagery strip close-up (top of the page after reload)
        await page.goto(URL, wait_until="networkidle", timeout=60_000)
        await page.wait_for_timeout(3000)
        await page.screenshot(path=str(OUT / "imagery.png"), clip={"x": 0, "y": 90, "width": 1280, "height": 420})

        await browser.close()
    print("done.")
    for p in sorted(OUT.glob("*.png")):
        kb = p.stat().st_size / 1024
        print(f"  {p.name:30}  {kb:6.0f} KB")


if __name__ == "__main__":
    asyncio.run(capture())
