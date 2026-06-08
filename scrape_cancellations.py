import asyncio
import json
import re
from datetime import datetime
from playwright.async_api import async_playwright

BASE_URL = "https://www.haysa.org/schedules"

# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------

def strip_score_suffix(name):
    """
    Removes trailing W/L from team names so cancellation keys
    match ICS keys exactly.
    """
    return re.sub(r"\s*[WL]\s*$", "", name.strip(), flags=re.IGNORECASE)


def is_number(s):
    return s.isdigit()


# ---------------------------------------------------------
# MAIN SCRAPER
# ---------------------------------------------------------

async def scrape_cancellations():
    cancellations = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Load schedules index
        await page.goto(BASE_URL, wait_until="networkidle")

        links = await page.locator('#SchedulesPageLayout a').all()
        schedule_links = []

        for link in links:
            href = await link.get_attribute("href")
            text = (await link.text_content() or "").strip()
            if href and "/schedule/" in href.lower():
                if href.startswith("/"):
                    href = "https://www.haysa.org" + href
                schedule_links.append((href, text))

        print(f"Found {len(schedule_links)} schedule links")

        # Process each division page
        for url, division in schedule_links:
            print(f"Processing: {division} -> {url}")

            try:
                await page.goto(url, wait_until="networkidle")

                # Scrape BOTH grids
                tables = await page.locator(
                    "table[id*='ScheduleGrid'], table[id*='MobileScheduleGrid']"
                ).all()

                if not tables:
                    print(f"  No schedule tables found for {division}")
                    continue

                for table in tables:
                    rows = await table.locator("tr").all()

                    for row in rows:
                        row_html = (await row.inner_html()) or ""
                        tds = await row.locator("td").all()

                        if len(tds) < 4:
                            continue

                        # Extract fields
                        date_text = (await tds[0].inner_text() or "").strip()
                        time_text = (await tds[1].inner_text() or "").strip()

                        raw_home = (await tds[2].inner_text() or "")
                        raw_away = (await tds[3].inner_text() or "")

                        # Normalize team names (strip W/L)
                        home_text = strip_score_suffix(raw_home)
                        away_text = strip_score_suffix(raw_away)

                        if not date_text or not time_text or not home_text or not away_text:
                            continue

                        # Detect cancellation (line-through)
                        is_cancelled = "text-decoration: line-through" in row_html.lower()

                        # Extract score spans
                        try:
                            home_score = (await tds[2].locator("span[id*='HomeScore']").inner_text() or "").strip().upper()
                        except:
                            home_score = ""

                        try:
                            away_score = (await tds[3].locator("span[id*='AwayScore']").inner_text() or "").strip().upper()
                        except:
                            away_score = ""

                        # Forfeit rule: BOTH scores must be W/L and NOT numbers
                        is_forfeit = (
                            home_score in ["W", "L"] and
                            away_score in ["W", "L"] and
                            not is_number(home_score) and
                            not is_number(away_score)
                        )

                        # Skip if neither cancelled nor forfeited
                        if not (is_cancelled or is_forfeit):
                            continue

                        # Normalize date
                        date_norm = date_text
                        try:
                            parts = date_text.split()
                            if len(parts) == 2:
                                _, md = parts
                                month, day = md.split("/")
                                now = datetime.now()
                                dt = datetime(now.year, int(month), int(day))
                                date_norm = dt.strftime("%A, %b %d")
                        except:
                            pass

                        # Build clean key (matches ICS)
                        key = f"{date_norm} | {time_text} | {home_text} | {away_text}"

                        cancellations[key] = {
                            "date": date_norm,
                            "time": time_text,
                            "home": home_text,
                            "away": away_text,
                            "type": "forfeit" if is_forfeit else "cancelled",
                            "home_score": home_score,
                            "away_score": away_score,
                            "raw_html": row_html,
                        }

            except Exception as e:
                print(f"  Error processing {division}: {e}")

        await browser.close()

    # Write output
    stamp = datetime.now().isoformat()
    output = {
        "generated_at": stamp,
        "source": BASE_URL,
        "cancellations": cancellations,
    }

    with open("cancellations.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"Written cancellations.json with {len(cancellations)} cancelled/forfeit games")


if __name__ == "__main__":
    asyncio.run(scrape_cancellations())
