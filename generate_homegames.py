import requests
from ics import Calendar
from datetime import datetime, timedelta
import ssl
from collections import defaultdict
import pytz
import re

# ---------------------------------------------------------
# TIMEZONE HELPERS
# ---------------------------------------------------------

def to_eastern(dt):
    eastern = pytz.timezone("US/Eastern")
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    return dt.astimezone(eastern)


# ---------------------------------------------------------
# ICS DOWNLOAD WITH BROWSER SPOOFING
# ---------------------------------------------------------

ssl._create_default_https_context = ssl._create_unverified_context

ICAL_URL = "http://tmsdln.com/19hyx"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "text/calendar,text/plain,*/*",
}

response = requests.get(ICAL_URL, headers=HEADERS, timeout=30, verify=False)
response.raise_for_status()

raw_bytes = response.content

# Try multiple decodings
for encoding in ["utf-8", "latin-1", "utf-16", "utf-16le", "utf-16be"]:
    try:
        calendar_data = raw_bytes.decode(encoding)
        if "BEGIN:VCALENDAR" in calendar_data:
            break
    except:
        continue

with open("ics_dump.txt", "w", encoding="utf-8") as dump:
    dump.write(calendar_data)

calendar = Calendar(calendar_data)


# ---------------------------------------------------------
# FIELD NORMALIZATION
# ---------------------------------------------------------

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
    "A-BU1": "Avon Butler Elementary School",
    "Avon Butler Elementary School": "Avon Butler Elementary School",
}

def normalize_field_name(location):
    loc = (location or "").strip()
    for alias, name in field_name_map.items():
        if alias.lower() in loc.lower():
            return name
    return loc


# ---------------------------------------------------------
# CREST MAPPING
# ---------------------------------------------------------

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

hayasa_crest = "https://d2jqoimos5um40.cloudfront.net/site_1563/162dca.png"


# ---------------------------------------------------------
# TEAM & OPPONENT DETECTION
# ---------------------------------------------------------

HOLBROOK_TRAVEL_PATTERN = re.compile(
    r"^\s*(\d+(?:/\d+)*(?:/PG)?)\s+(Boys|Girls)\b",
    re.IGNORECASE
)

OPPONENT_PATTERN = re.compile(r"^[A-Z][A-Z \-]+$")

VS_PATTERN = re.compile(r"\bvs\.?\b", re.IGNORECASE)


def is_holbrook_team(text):
    return bool(HOLBROOK_TRAVEL_PATTERN.match(text.strip()))


def is_opponent(text):
    return bool(OPPONENT_PATTERN.match(text.strip()))


def split_teams(name):
    name = name.strip()

    vs_match = VS_PATTERN.search(name)
    if vs_match:
        left = name[:vs_match.start()].strip()
        right = name[vs_match.end():].strip()
        return left, "vs", right

    if "@" in name:
        left, right = name.split("@", 1)
        return left.strip(), "@", right.strip()

    return None, None, None


# ---------------------------------------------------------
# DATE FILTERING (THIS WEEK)
# ---------------------------------------------------------

today = datetime.now(pytz.timezone("US/Eastern"))
this_monday = today - timedelta(days=today.weekday())
this_sunday = this_monday + timedelta(days=6)

games_by_day = defaultdict(list)
home_games_by_day = defaultdict(list)


# ---------------------------------------------------------
# PARSE EVENTS
# ---------------------------------------------------------

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

    left, sep, right = split_teams(name)
    if not left or not sep or not right:
        continue

    left_is_hay = is_holbrook_team(left)
    right_is_hay = is_holbrook_team(right)
    left_is_opp = is_opponent(left)
    right_is_opp = is_opponent(right)

    is_travel = (
        (left_is_hay and right_is_opp) or
        (right_is_hay and left_is_opp) or
        (left_is_hay and right_is_hay)
    )

    if not is_travel:
        continue

    if sep == "vs":
        is_home = left_is_hay
    else:
        is_home = right_is_hay

    if left_is_hay:
        hay_team = left
        opponent = right
    else:
        hay_team = right
        opponent = left

    opponent_clean = opponent.strip().upper()
    crest = opponent_crests.get(opponent_clean, "")

    game = {
        "team": hay_team,
        "opponent": opponent_clean,
        "location": location.strip(),
        "normalized_location": normalize_field_name(location),
        "time": time_str,
        "is_home": is_home,
        "crest": crest,
    }

    games_by_day[date_label].append(game)
    if is_home:
        home_games_by_day[date_label].append(game)


# ---------------------------------------------------------
# HTML RENDERING
# ---------------------------------------------------------

def format_last_updated():
    now = datetime.now(pytz.timezone("US/Eastern"))
    return now.strftime("%A, %B %d, %Y at %I:%M %p %Z")


def render_games(games_map):
    if not games_map:
        return "<p>No games this week!</p>"

    def parse_date(label):
        return datetime.strptime(label, "%A, %b %d").replace(year=today.year)

    html = []
    for date_label in sorted(games_map.keys(), key=parse_date):
        html.append(f"<h2>📅 {date_label}</h2>")
        html.append("<ul class='game-list'>")

        for g in sorted(games_map[date_label], key=lambda x: x["time"]):
            crest_html = f"<img src='{g['crest']}' class='crest'>" if g["crest"] else ""
            html.append(
                f"<li><strong>{g['time']}</strong> – "
                f"<img src='{hayasa_crest}' class='crest'>"
                f"{g['team']} vs. {g['opponent']} {crest_html} "
                f"{'🏠' if g['is_home'] else '🚌'} – "
                f"<strong>{g['normalized_location']}</strong></li>"
            )

        html.append("</ul>")

    return "\n".join(html)


def render_page(title, intro, games_map):
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
  body {{
    font-family: system-ui, sans-serif;
    margin: 0;
    padding: 1.5rem;
    background: #f5f5f5;
  }}
  .container {{
    max-width: 800px;
    margin: 0 auto;
    background: white;
    padding: 1.5rem;
    border-radius: 12px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.06);
  }}
  h1 {{ margin-top: 0; }}
  .game-list {{ list-style: none; padding-left: 0; }}
  .game-list li {{ margin: 0.4rem 0; }}
  img.crest {{ height: 1em; vertical-align: middle; margin: 0 0.3em; }}
  .updated {{ margin-top: 1.5rem; font-size: 0.85rem; color: #666; }}
</style>
</head>
<body>
<div class="container">
  <h1>{title}</h1>
  <p>{intro}</p>
  {render_games(games_map)}
  <p class="updated">Last updated: {format_last_updated()}</p>
</div>
</body>
</html>
"""


# ---------------------------------------------------------
# WRITE OUTPUT FILES
# ---------------------------------------------------------

home_html = render_page(
    "Holbrook Home Games",
    "These games are happening right here in Holbrook.",
    home_games_by_day
)

with open("home.html", "w", encoding="utf-8") as f:
    f.write(home_html)

all_html = render_page(
    "Holbrook Travel Schedule",
    "All Holbrook travel games this week — home and away.",
    games_by_day
)

with open("all_games.html", "w", encoding="utf-8") as f:
    f.write(all_html)
