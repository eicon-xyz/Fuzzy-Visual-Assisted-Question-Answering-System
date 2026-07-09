"""GitHub Trending Demo - Browser Snapshot Test
Quick check: what does browser_snapshot return on github.com/trending?
"""
import json, sys, os, time

sys.path.insert(0, ".")
# Use the actual BrowserController to test
import asyncio

async def main():
    from server.services.browser.controller import BrowserController

    browser = BrowserController()
    await browser.start(headless=False)

    # Navigate to GitHub Trending
    result = await browser.navigate("https://github.com/trending/python?since=daily")
    print(f"Navigate: {result.get('action_summary', result)[:200]}")

    # Wait for JS to render
    await asyncio.sleep(3)

    # Get snapshot
    snap = await browser.get_snapshot()
    print(f"\nTitle: {snap['title']}")
    print(f"URL: {snap['url']}")
    print(f"Elements: {snap.get('element_count', len(snap.get('elements', [])))} interactive")
    print(f"\nSnapshot text (first 3000 chars):")
    print(snap.get('snapshot_text', '')[:3000])

    # Print raw elements for analysis
    elements = snap.get('elements', [])
    print(f"\n\nFirst 20 raw elements:")
    for i, el in enumerate(elements[:20]):
        print(f"  [{i}] <{el.get('tag')}> text={el.get('text','')[:80]} selector={el.get('selector','')[:60]}")

    await browser.close()

asyncio.run(main())
