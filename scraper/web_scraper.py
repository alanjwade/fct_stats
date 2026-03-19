"""
Playwright-based web scraper for fetching meet results from MileSplit.

Fetches a results page and extracts all event tables into a structured JSON
format, which is cached at data/sources/<year>/pages/<slug>.json
so subsequent runs skip the network fetch.
"""

import asyncio
import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# JS snippet that extracts all result tables from the rendered page.
_EXTRACT_JS = """
() => {
    const allTables = document.querySelectorAll('table');
    const events = [];

    allTables.forEach((table) => {
        // Walk up the DOM to find the nearest event heading.
        let node = table.parentElement;
        let eventName = '';
        for (let depth = 0; depth < 8 && node && !eventName; depth++) {
            const headings = node.querySelectorAll(
                'h1,h2,h3,h4,h5,.eventName,.event-name,.section-title'
            );
            if (headings.length > 0) {
                eventName = headings[0].innerText.trim();
            }
            node = node.parentElement;
        }

        // Column headers from <thead>
        const headerCells = table.querySelectorAll('thead th');
        const headers = Array.from(headerCells).map(th => th.innerText.trim());

        // Data rows from <tbody>
        const tbody = table.querySelector('tbody');
        if (!tbody) return;
        const rows = tbody.querySelectorAll('tr');
        const rowData = [];
        rows.forEach(tr => {
            const cells = tr.querySelectorAll('td');
            const cellTexts = Array.from(cells).map(td => td.innerText.trim());
            if (cellTexts.some(t => t)) {
                rowData.push(cellTexts);
            }
        });

        if (rowData.length > 0) {
            events.push({ event: eventName, headers: headers, rows: rowData });
        }
    });
    return events;
}
"""


def get_pages_dir(year: int, data_dir: Path) -> Path:
    """Return (and create) the cache directory for a given year."""
    pages_dir = data_dir / 'sources' / str(year) / 'pages'
    pages_dir.mkdir(parents=True, exist_ok=True)
    return pages_dir


def url_to_slug(url: str) -> str:
    """
    Derive a cache filename slug from a URL.

    For a MileSplit URL like:
        https://co.milesplit.com/meets/709570-john-martin-early-bird-invite-2026/results
    the slug will be:
        709570-john-martin-early-bird-invite-2026
    For other URLs the full path is slugified.
    """
    # Try to pull the meet segment from a MileSplit-style URL.
    m = re.search(r'/meets/([^/?#]+)', url)
    if m:
        return m.group(1)
    # Generic fallback: lowercase + safe chars.
    return re.sub(r'[^a-z0-9\-]+', '-', url.lower()).strip('-')


def get_cache_path(url: str, year: int, data_dir: Path) -> Path:
    """Return the cache file path for a given URL."""
    slug = url_to_slug(url)
    return get_pages_dir(year, data_dir) / f"{slug}.json"


async def _fetch_page(url: str) -> dict:
    """
    Use Playwright / Chromium to load *url* and extract all result tables.
    Returns a dict suitable for JSON serialisation.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError(
            "playwright is not installed. Run: pip install playwright && playwright install chromium"
        ) from exc

    logger.info("Launching headless Chromium to scrape %s", url)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )
        )
        page = await ctx.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            logger.warning("Page load did not complete cleanly (%s); proceeding anyway", e)

        # Allow JS-rendered content to settle.
        await page.wait_for_timeout(5000)

        title = await page.title()
        events = await page.evaluate(_EXTRACT_JS)
        await browser.close()

    logger.info("Scraped %d event tables from %s", len(events), title)
    return {
        "url": url,
        "title": title,
        "scraped_with": "playwright",
        "events": events,
    }


def scrape_url(url: str, year: int, data_dir: Path, force: bool = False) -> Path:
    """
    Fetch *url* (or return the cached result) and write a JSON file to
    data/sources/<year>/pages/<slug>.json.

    Args:
        url:      Full results URL.
        year:     Meet year — used to place the file in the right subdirectory.
        data_dir: Root data directory of the project.
        force:    Re-scrape even if a cached file already exists.

    Returns:
        Path to the (possibly newly created) cached JSON file.
    """
    cache_path = get_cache_path(url, year, data_dir)

    if cache_path.exists() and not force:
        logger.info("Using cached scrape: %s", cache_path)
        return cache_path

    data = asyncio.run(_fetch_page(url))

    with open(cache_path, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)

    logger.info("Saved scraped data to %s", cache_path)
    return cache_path


def load_cached(url: str, year: int, data_dir: Path) -> dict | None:
    """
    Load previously scraped JSON for *url* without hitting the network.
    Returns None if no cache exists.
    """
    cache_path = get_cache_path(url, year, data_dir)
    if not cache_path.exists():
        return None
    with open(cache_path, 'r', encoding='utf-8') as fh:
        return json.load(fh)
