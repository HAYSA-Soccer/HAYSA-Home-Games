import requests
from ics import Calendar
from datetime import datetime, timedelta
import ssl
from collections import defaultdict
import pytz
import re

# --- Timezone helpers ---
def to_eastern(dt):
    eastern = pytz.timezone("US/Eastern")
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    return dt.astimezone(eastern)


# --- FIXED ICS DOWNLOAD (handles file-download responses) ---
ssl._create_default_https_context = ssl._create_unverified_context

ICAL_URL = "http://tmsdln.com/19hyx"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

response = requests.get(ICAL_URL, headers=HEADERS)
response.raise_for_status()

# Read raw bytes instead of response.text
raw_bytes = response.content

# Try UTF‑8 first, fallback to Latin‑1
try:
    calendar_data = raw_bytes.decode("utf-8", errors="ignore")
except:
    calendar_data = raw_bytes.decode("latin-1", errors="ignore")

# Debug dump
with open("ics_dump.txt", "w", encoding="utf-8") as dump:
    dump.write(calendar_data)

# Parse ICS
calendar = Calendar(calendar_data)


# --- Field normalization (display only) ---
field_name_map = {
    "H-HST": "Holbrook High School",
    "Holbrook HS": "Holbrook High School",
    "Holbrook High School": "Holbrook High School",
    "143 S Franklin St": "Holbrook High School",
    "143 South Franklin Street": "Holbrook High School",
    "Sean Joyce Field": "Sean Joyce Field",
    "Sumner Field": "Sean Joyce Field",
    "Holbrook Playground": "Sean Joyce Field",
    "H-SJ4": "Sean Joyce Field",
}

def normalize_field_name(location: str) -> str:
    loc = (location or "").strip()
    for alias, name in field_name_map.items():
        if alias.lower() in loc.lower():
            return name
    return loc


# --- Crest Mapping ---
opponent_crests = {
    "ABINGTON": "https://static.wixstatic.com/media/97261c_54471fdb634c4d3fa113fe951de314ef~mv2.png",
    "ACUSHNET": "https://nebula.wsimg.com/d34af03927e1352f5052348865f537ac",
    "BRAINTREE": "https://tse4.mm.bing.net/th/id/OIP.8mgnbl-_HFeJrpvFPBck9AHaHa",
    "BRIDGEWATER": "https://www.bridgewateryouthsoccer.com/Portals/4899/logo/logo636223303834986882.png",
    "COHASSET": "https://tse3.mm.bing.net/th/id/OIP.GGHkIzybTl-3dbqcY51nVAHaJj",
    "EAST BRIDGEWATER": "https://www.ebysa.com/Portals/57/EBYSA%20Web%20Heading%20Narrow%20Large.png",
    "EASTON": "https://cdn1.sportngin.com/attachments/call_to_action/4dc7-210934873/EYSL_Ball_large.png",
    "HANSON": "https://whitmanhansonyouthsoccer.org/Portals/19/image001.png",
    "WHITMAN-HANSON": "https://whitmanhansonyouthsoccer.org/Portals/19/image001.png",
    "MARSHFIELD": "https://www.marshfieldsoccer.com/wp-content/uploads/sites/678/2022/05/MYS_Full_Color_Black_White_LizardNeonGreen.png",
    "MMR": "https://www.marionma.gov/ImageRepository/Document?documentID=72",
    "MIDDLEBORO": "https://images.squarespace-cdn.com/content/v1/5592f956e4b0d217906ce58b/1530823172680-BO9CXY334H3TYWM0M1A6/logo.png",
    "PLYMOUTH": "https://nebula.wsimg.com/78a7bc57d1d03265f333a66707a25638",
    "QUINCY": "https://tse2.mm.bing.net/th/id/OIP.CZdNrzdApKNlAj0QhyKmVAAAAA",
    "RANDOLPH": "https://www.wegotsoccer.com/mmWGS/team/randolph/randolph-logo.png",
    "RAYNHAM": "https://raynhamsoccer.com/wp-content/uploads/2023/02/RAYNHAM-LOGO.png",
    "ROCKLAND": "https://tse1.mm.bing.net/th/id/OIP.624YgOq0bVdVkfJOolTAmgAAAA",
    "SHARON": "https://images.squarespace-cdn.com/content/v1/66a28a811406ea11d1e561df/4f0e039a-9230-4471-982b-0e549d47727d/SSA_Logo_Transparent.png",
    "SILVER LAKE": "https://image.maxpreps.io/school-mascot/a/3/d/a3d4d72f-2659-4933-9947-94149c2a5b0b.gif",
    "STOUGHTON": "https://stoughtonsoccer.org/Portals/68/logo_transparent.png",
    "WEST BRIDGEWATER": "https://www.wbyaa.com/Portals/52208/logo638573245926682379.png",
    "WEYMOUTH": "https://weymouthsite.sportspilot.com/portals/47/Images/WYS%20Logo_small.jpg",
}


# --- Travel / Rec detection patterns ---
HOLBROOK_TRAVEL_PATTERN = re.compile(
    r'^\s*\d+(?:/\d+)*(?:/PG)?\s+(?:Boys|Girls)\b',
    re.IGNORECASE,
)

OPPONENT_PATTERN = re.compile(r'^[A-Z][A-Z \-]+$')
VS_SEPARATOR_PATTERN = re.compile(r'\bvs\.?\b', re.IGNORECASE)


def is_holbrook_travel_team(text: str) -> bool:
    return bool(HOLBROOK_TRAVEL_PATTERN.match(text.strip()))


def is_travel_opponent(text: str) -> bool:
    return bool(OPPONENT_PATTERN.match(text.strip()))


def split_teams(summary: str):
    name = (summary or "").strip()

    vs_match = VS_SEPARATOR_PATTERN.search(name)
    if vs_match:
        sep = "vs"
        left = name[:vs_match.start()].strip()
        right = name[vs_match.end():].strip()
        if left and right:
            return left, sep, right

    if "@" in name:
        left, right = name.split("@", 1)
        return left.strip(), "@", right.strip()

    return None, None, None


# --- Date Filtering (this week: Monday–Sunday, Eastern) ---
today = datetime.now(pytz.timezone("US/Eastern"))
this_monday = today - timedelta(days=today.weekday())
this_sunday = this_monday + timedelta(days=6)

# --- Parse Events ---
games_by_day = defaultdict(list)
home_games_by_day = defaultdict(list)

for event in calendar.events:
    name = event.name or ""
    if "practice" in name.lower():
        continue

    start = to_eastern(event.begin.datetime)
    if not (this_monday.date() <= start.date() <= this_sunday.date()):
        continue

    location = event.location or ""
    time_str = start.strftime("%I:%M %p").lstrip("0")
    date_label = start.strftime("%A, %b %d")

    left, separator, right = split_teams(name)
    if not left or not separator or not right:
        continue

    left_is_holbrook = is_holbrook_travel_team(left)
    right_is_holbrook = is_holbrook_travel_team(right)
    left_is_opponent = is_travel_opponent(left)
    right_is_opponent = is_travel_opponent(right)

    is_travel = (
        (left_is_holbrook and right_is_opponent) or
        (right_is_holbrook and left_is_opponent) or
        (left_is_holbrook and right_is_holbrook)
    )
    if not is_travel:
        continue

    if separator == "vs":
        is_home = left_is_holbrook
    else:
        is_home = right_is_holbrook

    if left_is_holbrook:
        hay_team = left
        opponent = right
    else:
        hay_team = right
        opponent = left

    m = re.search(r'\b([A-Z][A-Z \-]+)\b', opponent)
    opponent_clean = m.group(1).strip() if m else opponent.strip()

    crest = opponent_crests.get(opponent_clean.upper(), "")

    game = {
        "team": hay_team,
        "opponent": opponent_clean,
        "location": location.strip(),
        "time": time_str,
        "is_home": is_home,
        "normalized_location": normalize_field_name(location),
        "crest": crest,
    }

    games_by_day[date_label].append(game)
    if is_home:
        home_games_by_day[date_label].append(game)


# --- HTML Rendering Helpers ---
def format_last_updated() -> str:
    now = datetime.now(pytz.timezone("US/Eastern"))
    return now.strftime("%A, %B %d, %Y at %I:%M %p %Z")


def render_games_section(games_map: dict) -> str:
    if not games_map:
        return "<p>No games this week!</p>"

    def parse_label(label: str):
        return datetime.strptime(label, "%A, %b %d").replace(year=today.year)

    sections = []
    for date_label in sorted(games_map.keys(), key=parse_label):
        games = games_map[date_label]
        sections.append(f'<h2>📅 {date_label}</h2>')
        sections.append('<ul class="game-list">')
        for g in sorted(games, key=lambda x: x["time"]):
            sections.append(
                f'<li><strong>{g["time"]}</strong> – ⚽ {g["team"]} vs. {g["opponent"]} '
                f'{"🏠" if g["is_home"] else "🚌"} – <strong>{g["normalized_location"]}</strong></li>'
            )
        sections.append("</ul>")

    return "\n".join(sections)


def render_page(title: str, intro: str, games_map: dict) -> str:
    last_updated = format_last_updated()
    games_html = render_games_section(games_map)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>{title}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    body {{
      font-family: system-ui, sans-serif;
      margin: 0;
      padding: 1.5rem;
      background: #f5f5f5;
      color: #222;
    }}
    .container {{
      max-width: 800px;
      margin: 0 auto;
      background: #ffffff;
      padding: 1.5rem;
      border-radius: 12px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.06);
    }}
    h1 {{
      margin-top: 0;
      font-size: 1.6rem;
    }}
    h2 {{
      margin-top: 1.5rem;
      font-size: 1.2rem;
      color: #333;
    }}
    .game-list {{
      list-style: none;
      padding-left: 0;
    }}
    .game-list li {{
      margin: 0.4rem 0;
    }}
    .updated {{
      margin-top: 1.5rem;
      font-size: 0.85rem;
      color: #666;
    }}
  </style>
</head>
<body>
  <div class="container">
    <h1>{title}</h1>
    <p>{intro}</p>
    {games_html}
    <p class="updated">Last updated: {last_updated}</p>
  </div>
</body>
</html>
"""


# --- Generate home.html ---
home_intro = (
    "Looking for a quick sideline stop this week? These games are happening right here in Holbrook—"
    "bring a chair, grab a coffee, and help make the sidelines feel like home!"
)
home_html = render_page("Holbrook Home Games", home_intro, home_games_by_day)
with open("home.html", "w", encoding="utf-8") as f:
    f.write(home_html)

# --- Generate all_games.html ---
all_intro = (
    "Here are all Holbrook travel games for this week—home and away—so you can follow every team."
)
all_html = render_page("Holbrook Travel Schedule", all_intro, games_by_day)
with open("all_games.html", "w", encoding="utf-8") as f:
    f.write(all_html)
