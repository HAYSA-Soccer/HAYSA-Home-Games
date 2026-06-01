import asyncio
import json
from datetime import datetime

from playwright.async_api import async_playwright

BASE_URL = "https://www.haysa.org/schedules"


async def scrape_cancellations():
    cancellations = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # 1) Load schedules index and collect division links
        await page.goto(BASE_URL, wait_until="networkidle")

        links = await page.locator('#SchedulesPageLayout a').all()
        schedule_links = []
        for link in links:
            href = await link.get_attribute("href")
            text = (await link.text_content() or "").strip()
            if href and "/schedule/" in href.lower():
                # Make absolute if needed
                if href.startswith("/"):
                    href = "https://www.haysa.org" + href
                schedule_links.append((href, text))

        print(f"Found {len(schedule_links)} schedule links")

        # 2) Visit each division page and detect cancelled games
        for url, division in schedule_links:
            print(f"Processing: {division} -> {url}")
            try:
                await page.goto(url, wait_until="networkidle")

                table = page.locator("table[id*='ScheduleGrid']")
                if not await table.count():
                    print(f"  No schedule table found for {division}")
                    continue

                rows = await table.locator("tr").all()

                for row in rows:
                    row_html = (await row.inner_html()) or ""
                    # Skip header / non-data rows
                    tds = await row.locator("td").all()
                    if len(tds) < 4:
                        continue

                    # Extract text cells
                    date_text = (await tds[0].inner_text() or "").strip()
                    time_text = (await tds[1].inner_text() or "").strip()
                    home_text = (await tds[2].inner_text() or "").strip()
                    away_text = (await tds[3].inner_text() or "").strip()
                    location_text = (await tds[4].inner_text() or "").strip() if len(tds) > 4 else ""

                    if not date_text or not time_text or not home_text or not away_text:
                        continue

                    # Normalize date to something stable (keep as-is for now)
                    # Example: "Sat 5/30" -> we keep that string; ICS side will need to align
                    date_norm = date_text
                    time_norm = time_text
                    home_norm = home_text
                    away_norm = away_text

                    # Detect cancellation via line-through formatting
                    is_cancelled = "text-decoration: line-through" in row_html.lower()

                    if not is_cancelled:
                        continue  # we only store cancelled games

                    from datetime import datetime

                    # Convert "Sat 5/30" → "Saturday, May 30"
                    date_ics = date_norm  # fallback
                    
                    try:
                        parts = date_norm.split()
                        if len(parts) == 2:
                            dow, md = parts
                            month, day = md.split("/")
                            month = int(month)
                            day = int(day)
                    
                            now = datetime.now()
                            dt = datetime(now.year, month, day)
                    
                            date_ics = dt.strftime("%A, %b %d")
                    except Exception as e:
                        print(f"  Date parse failed for '{date_norm}': {e}")

                    
                    key = f"{date_ics} | {time_norm} | {home_norm} | {away_norm}"

                    cancellations[key] = {
                        "date": date_ics,
                        "time": time_norm,
                        "home": home_norm,
                        "away": away_norm
                    }


            except Exception as e:
                print(f"  Error processing {division}: {e}")

        await browser.close()

    # 3) Write cancellations.json in repo root
    stamp = datetime.now().isoformat()
    output = {
        "generated_at": stamp,
        "source": BASE_URL,
        "cancellations": cancellations,
    }

    with open("cancellations.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"Written cancellations.json with {len(cancellations)} cancelled games")


if __name__ == "__main__":
    asyncio.run(scrape_cancellations())
