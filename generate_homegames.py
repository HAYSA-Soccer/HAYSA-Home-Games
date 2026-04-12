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


# --- iCal Feed (browser user-agent only, NO cache-busting) ---
ssl._create_default_https_context = ssl._create_unverified_context

ICAL_URL = "http://tmsdln.com/19hyx"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

response = requests.get(ICAL_URL, headers=HEADERS)
response.raise_for_status()
calendar_data = response.text

# --- DEBUG: Dump ICS feed so we can see what GitHub Actions is receiving ---
# (Make sure ics_dump.txt is in .gitignore)
with open("ics_dump.txt", "w", encoding="utf-8") as dump:
    dump.write(calendar_data)

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
    # Avon Butler, etc., can be added here if you want to normalize those too
}

def normalize_field_name(location: str) -> str:
    loc = (location or "").strip()
    for alias, name in field_name_map.items():
        if alias.lower() in loc.lower():
            return name
    return loc


# --- Crest Mapping ---
hayasa_crest = "https://d2jqoimos5um40.cloudfront.net/site_1563/162dca.png"
opponent_crests = {
    "ABINGTON": "https://static.wixstatic.com/media/97261c_54471fdb634c4d3fa113fe951de314ef~mv2.png/v1/fill/w_174,h_204,al_c,q_85,usm_0.66_1.00_0.01,enc_avif,quality_auto/97261c_54471fdb634c4d3fa113fe951de314ef~mv2.png",
    "ACUSHNET": "https://nebula.wsimg.com/d34af03927e1352f5052348865f537ac?AccessKeyId=8C796AAE797710F94A84&disposition=0&alloworigin=1",
    "BRAINTREE": "https://tse4.mm.bing.net/th/id/OIP.8mgnbl-_HFeJrpvFPBck9AHaHa?pid=Api&P=0&h=180",
    "BRIDGEWATER": "https://www.bridgewateryouthsoccer.com/Portals/4899/logo/logo636223303834986882.png",
    "COHASSET": "https://tse3.mm.bing.net/th/id/OIP.GGHkIzybTl-3dbqcY51nVAHaJj?pid=Api&P=0&h=180",
    "EAST BRIDGEWATER": "https://www.ebysa.com/Portals/57/EBYSA%20Web%20Heading%20Narrow%20Large.png?ver=Pw7zgypKOiIftXloW6Hg0w%3d%3d",
    "EASTON": "https://cdn1.sportngin.com/attachments/call_to_action/4dc7-210934873/EYSL_Ball_large.png",
    "HANSON": "https://whitmanhansonyouthsoccer.org/Portals/19/image001.png?ver=MY_OEzOjTRl4maigQFKbVg%3d%3d",
    "WHITMAN-HANSON": "https://whitmanhansonyouthsoccer.org/Portals/19/image001.png?ver=MY_OEzOjTRl4maigQFKbVg%3d%3d",
    "MARSHFIELD": "https://www.marshfieldsoccer.com/wp-content/uploads/sites/678/2022/05/MYS_Full_Color_Black_White_LizardNeonGreen.png",
    "MMR": "https://www.marionma.gov/ImageRepository/Document?documentID=72",
    "MIDDLEBORO": "https://images.squarespace-cdn.com/content/v1/5592f956e4b0d217906ce58b/1530823172680-BO9CXY334H3TYWM0M1A6/logo.png?format=1500w",
    "PLYMOUTH": "https://nebula.wsimg.com/78a7bc57d1d03265f333a66707a25638?AccessKeyId=63688D9BB3B532ACAA07&disposition=0&alloworigin=1",
    "QUINCY": "https://tse2.mm.bing.net/th/id/OIP.CZdNrzdApKNlAj0QhyKmVAAAAA?pid=Api&P=0&h=180",
    "RANDOLPH": "https://www.wegotsoccer.com/mmWGS/team/randolph/randolph-logo.png",
    "RAYNHAM": "https://raynhamsoccer.com/wp-content/uploads/2023/02/RAYNHAM-LOGO.png",
    "ROCKLAND": "https://tse1.mm.bing.net/th/id/OIP.624YgOq0bVdVkfJOolTAmgAAAA?pid=Api&P=0&h=180",
    "SHARON": "https://images.squarespace-cdn.com/content/v1/66a28a811406ea11d1e561df/4f0e039a-9230-4471-982b-0e549d47727d/SSA_Logo_Transparent.png?format=1500w",
    "SILVER LAKE": "https://image.maxpreps.io/school-mascot/a/3/d/a3d4d72f-2659-4933-9947-94149c2a5b0b.gif?version=635801467800000000&width=128&height=128&auto=webp&format=pjpg",
    "STOUGHTON": "https://stoughtonsoccer.org/Portals/68/logo_transparent.png?ver=2021-09-08-100316-333",
    "WEST BRIDGEWATER": "https://www.wbyaa.com/Portals/52208/logo638573245926682379.png",
    "WEYMOUTH": "https://weymouthsite.sportspilot.com/portals/47/Images/WYS%20Logo_small.jpg",
}

# --- Travel / Rec detection patterns ---

# Holbrook travel team formats in ICS:
#   "5/6 Girls (Baird-Miller)"
#   "3/4 Boys (Walsh)"
#   "11/12/PG Girls Travel (Green)"
#   "9/10 Boys Lauterhahn"
#   "7/8 Boys (Mills)"
HOLBROOK_TRAVEL_PATTERN = re.compile(
    r'^\s*\d+(?:/\d+)*(?:/PG)?\s+(?:Boys|Girls)\b',
    re.IGNORECASE,
)

# Opponents are ALL CAPS words with spaces/hyphens:
OPPONENT_PATTERN = re.compile(r'^[A-Z][A-Z \-]+$')

# Separator: "vs", "vs.", "VS", "VS.", "@"
VS_SEPARATOR_PATTERN = re.compile(r'\bvs\.?\b', re.IGNORECASE)


def is_holbrook_travel_team(text: str) -> bool:
    return bool(HOLBROOK_TRAVEL_PATTERN.match(text.strip()))


def is_travel_opponent(text: str) -> bool:
    return bool(OPPONENT_PATTERN.match(text.strip()))


def split_teams(summary: str):
    """
    Split an event SUMMARY into (left, separator, right).
    Supports:
      - "Holbrook Team vs. OPPONENT"
      - "OPPONENT vs. Holbrook Team"
      - "Holbrook Team @ OPPONENT"
      - "OPPONENT @ Holbrook Team"
    Returns (left, sep, right) or (None, None, None) if not parseable.
    """
    name = summary or ""
    name = name.strip()

    # Try vs/vs./VS/VS.
    vs_match = VS_SEPARATOR_PATTERN.search(name)
    if vs_match:
        sep = "vs"
        idx = vs_match.start()
        left = name[:idx].strip()
        right = name[vs_match.end():].strip()
        if left and right:
            return left, sep, right

    # Fallback: "@"
    if "@" in name:
        parts = name.split("@", 1)
        left = parts[0].strip()
        right = parts[1].strip()
        if left and right:
            return left, "@", right

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
        # Not a recognizable game format
        continue

    # Travel detection
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

    # Determine home/away
    if separator == "vs":
        # "Holbrook vs Opponent" => Holbrook home
        is_home = left_is_holbrook
    elif separator == "@":
        # "Holbrook @ Opponent" => Holbrook away
        # "Opponent @ Holbrook" => Holbrook home
        is_home = right_is_holbrook
    else:
        # Shouldn't happen, but be explicit
        is_home = False

    # Assign Holbrook team + opponent
    if left_is_holbrook:
        hay_team = left
        opponent = right
    else:
        hay_team = right
        opponent = left

    opponent_clean = opponent.strip()
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
