import re
import requests
from ics import Calendar
from datetime import datetime, timedelta
from collections import defaultdict
import pytz

# ---------------------------------------------------------
# ICS FETCH (DIRECT, NO CLOUDFLARE)
# ---------------------------------------------------------

ICAL_URL = "https://calendar.teamsideline.com/ical?d=vseBS5X6j9qQXmVOavlTZkdNQFag+DgzH/UkvFJa2mpTE5JTsKoabQ=="

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

response = requests.get(ICAL_URL, headers=headers)
response.raise_for_status()
calendar_data = response.text

with open("ics_dump.txt", "w", encoding="utf-8") as dump:
    dump.write(calendar_data)

calendar = Calendar(calendar_data)

# ---------------------------------------------------------
# TIMEZONE HELPERS
# ---------------------------------------------------------

def to_eastern(dt):
    eastern = pytz.timezone("US/Eastern")
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    return dt.astimezone(eastern)

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
    "HANOVER": "https://cdn4.sportngin.com/attachments/call_to_action/eca2-187898068/CleanShot_2023-04-06_at_14.19.53_2x_large.png",

}   

hayasa_crest = "https://d2jqoimos5um40.cloudfront.net/site_1563/162dca.png"

# ---------------------------------------------------------
# TEAM & OPPONENT DETECTION
# ---------------------------------------------------------

HOLBROOK_TRAVEL_PATTERN = re.compile(
    r"^\s*\d+(?:/\d+)*(?:/PG)?\s+(Boys|Girls)\b.*",
    re.IGNORECASE
)

def is_holbrook_team(text):
    return bool(HOLBROOK_TRAVEL_PATTERN.match(text.strip()))

def is_opponent(text):
    t = text.strip().upper()
    t = re.sub(r"\(.*?\)", "", t)  # remove (Green), (Blue), etc.
    t = t.replace("–", "-").replace("—", "-")
    t = re.sub(r"\s+", " ", t)

    # Exact match
    if t in opponent_crests:
        return True

    # Prefix match (handles "HANOVER U12", "HANOVER (Green)", etc.)
    for key in opponent_crests.keys():
        if t.startswith(key):
            return True

    return False


def split_teams(name):
    name = name.strip()
    name = name.replace("\u00A0", " ")
    name = name.replace("–", "-").replace("—", "-")

    match = re.search(r"\b(vs?|VS?)[\.\s]*\b|@", name)
    if not match:
        return None, None, None

    sep = match.group(0).strip().lower()
    left = name[:match.start()].strip()
    right = name[match.end():].strip()

    return left, sep, right

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

    # CLEAN TEAM NAMES BEFORE DETECTION
    clean_left = re.sub(r"\(.*?\)", "", left).strip()
    clean_right = re.sub(r"\(.*?\)", "", right).strip()

    # CLEAN OPPONENT NAMES BEFORE DETECTION
    clean_left_opp = re.sub(r"\(.*?\)", "", left).strip().upper()
    clean_right_opp = re.sub(r"\(.*?\)", "", right).strip().upper()

    left_is_hay = is_holbrook_team(clean_left)
    right_is_hay = is_holbrook_team(clean_right)
    left_is_opp = is_opponent(clean_left_opp)
    right_is_opp = is_opponent(clean_right_opp)

    is_travel = (
        (left_is_hay and right_is_opp) or
        (right_is_hay and left_is_opp) or
        (left_is_hay and right_is_hay)
    )

    if not is_travel:
        continue

    if sep.startswith("v"):
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
        "opponent_display": ("vs. " + opponent_clean) if is_home else ("@ " + opponent_clean),
        "location": location.strip(),
        "normalized_location": normalize_field_name(location),
        "time": time_str,
        "time_str": time_str,
        "start_dt": start,
        "is_home": is_home,
        "crest": crest,
    }

    games_by_day[date_label].append(game)
    if is_home:
        home_games_by_day[date_label].append(game)

# ---------------------------------------------------------
# HTML RENDERING
# ---------------------------------------------------------

def html_header(title):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="stylesheet" href="style.css">
</head>
<body>
<div class="schedule">
<h1 class="page-title">{title}</h1>
"""

def html_footer():
    now = datetime.now(pytz.timezone("US/Eastern"))
    stamp = now.strftime("%A, %B %d, %Y at %I:%M %p %Z")
    return f"""
<div class="last-updated">Last updated: {stamp}</div>
</div>
</body>
</html>
"""

def render_game(g, home_or_away):
    if g["is_home"]:
        home_team = g["team"]
        home_crest = hayasa_crest

        away_team = g["opponent"]
        away_crest = g["crest"]
    else:
        home_team = g["opponent"]
        home_crest = g["crest"]

        away_team = g["team"]
        away_crest = hayasa_crest

    home_crest_html = f"<img class='crest' src='{home_crest}'>" if home_crest else ""
    away_crest_html = f"<img class='crest' src='{away_crest}'>" if away_crest else ""

    return f"""
    <div class="game {home_or_away}">
      <span class="time">{g['time_str']}</span>

      {home_crest_html}
      <span class="team">{home_team}</span>

      <span class="opponent">vs.</span>

      {away_crest_html}
      <span class="team">{away_team}</span>

      <span class="location">{g['normalized_location']}</span>
    </div>
    """

def render_day_block(date_str, home_games, away_games):
    html = [f'<div class="day-block">']
    html.append(f'<h2 class="day-header">📅 {date_str}</h2>')

    html.append('<div class="section-header">🏠 Home Games</div>')
    if home_games:
        for g in sorted(home_games, key=lambda x: x["start_dt"]):
            html.append(render_game(g, "home"))
    else:
        html.append('<div class="no-games">No home games.</div>')

    html.append('<div class="section-header">🚐 Away Games</div>')
    if away_games:
        for g in sorted(away_games, key=lambda x: x["start_dt"]):
            html.append(render_game(g, "away"))
    else:
        html.append('<div class="no-games">No away games.</div>')

    html.append('</div>')
    return "\n".join(html)

def generate_home_html(days):
    html = [html_header("Holbrook Home Games")]
    html.append('<p class="subtitle">These games are happening right here in Holbrook.</p>')
    
    # Add link to full schedule
    html.append('<p style="text-align:center; margin-top:-1em;">')
    html.append('<a href="all_games.html" style="color:#004080; font-weight:600;">See all travel games (home & away)</a>')
    html.append('</p>')



    def parse_date(label):
        return datetime.strptime(label, "%A, %b %d").replace(year=today.year)

    for date_str in sorted(days.keys(), key=parse_date):
        home_games = [g for g in days[date_str] if g["is_home"]]
        if home_games:
            html.append(render_home_day_block(date_str, home_games))

    html.append(html_footer())

    with open("home.html", "w", encoding="utf-8") as f:
        f.write("\n".join(html))

def render_home_day_block(date_str, home_games):
    html = [f'<div class="day-block">']
    html.append(f'<h2 class="day-header">📅 {date_str}</h2>')

    html.append('<div class="section-header">🏠 Home Games</div>')
    for g in sorted(home_games, key=lambda x: x["start_dt"]):
        html.append(render_game(g, "home"))

    html.append('</div>')
    return "\n".join(html)


def generate_all_games_html(days):
    html = [html_header("Holbrook Travel Games")]
    html.append('<p class="subtitle">All Holbrook travel games this week — home and away.</p>')

    def parse_date(label):
        return datetime.strptime(label, "%A, %b %d").replace(year=today.year)

    for date_str in sorted(days.keys(), key=parse_date):
        games = days[date_str]
        home_games = [g for g in games if g["is_home"]]
        away_games = [g for g in games if not g["is_home"]]
        html.append(render_day_block(date_str, home_games, away_games))

    html.append(html_footer())

    with open("all_games.html", "w", encoding="utf-8") as f:
        f.write("\n".join(html))

# ---------------------------------------------------------
# WRITE OUTPUT FILES
# ---------------------------------------------------------

generate_home_html(games_by_day)
generate_all_games_html(games_by_day)
