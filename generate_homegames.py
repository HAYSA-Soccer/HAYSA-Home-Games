import os
import re
import json
import requests
from ics import Calendar
from datetime import datetime, timedelta
from collections import defaultdict
import pytz
import csv
from io import StringIO

# ---------------------------------------------------------
# LOAD CANCELLATIONS
# ---------------------------------------------------------

try:
    with open("cancellations.json", "r", encoding="utf-8") as f:
        cancellation_data = json.load(f)
        cancellations = cancellation_data.get("cancellations", {})
        print("Cancellations keys loaded:", len(cancellations))
        # Show a couple of sample keys
        for i, k in enumerate(cancellations.keys()):
            print("  cancellation key:", k)
            if i >= 4:
                break

except FileNotFoundError:
    print("WARNING: cancellations.json not found — assuming no cancellations.")
    cancellations = {}

# ---------------------------------------------------------
# CREST MAP FROM GOOGLE SHEET
# ---------------------------------------------------------

def load_crest_map_from_google_sheet(sheet_csv_url):
    response = requests.get(sheet_csv_url)
    response.raise_for_status()

    csv_data = response.text
    reader = csv.DictReader(StringIO(csv_data))

    crest_map = {}

    for row in reader:
        town = row["Town"].strip().upper()
        file_id = row["FileID"].strip()
        crest_url = f"https://drive.google.com/uc?export=view&id={file_id}"
        crest_map[town] = crest_url

    return crest_map

# ---------------------------------------------------------
# ICS FETCH
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
    "Brookville": "Brookville Fields",
}

def normalize_field_name(location):
    loc = (location or "").strip()
    for alias, name in field_name_map.items():
        if alias.lower() in loc.lower():
            return name
    return loc

def get_local_crest(opponent_name):
    slug = opponent_name.strip().upper().replace(" ", "_")
    path = f"assets/crests/{slug}.png"
    return path if os.path.exists(path) else ""

# ---------------------------------------------------------
# CREST MAPPING
# ---------------------------------------------------------

SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRu2yQBMvIYVuK7f7SdHkRHbexYLTKRiQoGe0mHtb7QRHQWZc0ekbabhrbGn9gI02zBywIFNQjnon9h/pub?gid=0&single=true&output=csv"

opponent_crests = load_crest_map_from_google_sheet(SHEET_CSV_URL)

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
    t = re.sub(r"\(.*?\)", "", t)
    t = t.replace("–", "-").replace("—", "-")
    t = re.sub(r"\s+", " ", t)

    if t in opponent_crests:
        return True

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
ics_games = {}  # key -> game

# ---------------------------------------------------------
# PARSE ICS EVENTS
# ---------------------------------------------------------

for event in calendar.events:
    name = event.name or ""
    if "practice" in name.lower():
        continue

    start = to_eastern(event.begin.datetime)
    in_window = this_monday.date() <= start.date() <= this_sunday.date()
    if not in_window:
        # Debug: show what we're skipping
        print("SKIP (date):", start.date(), "| name:", event.name)
        continue


    location = event.location or ""
    time_str = start.strftime("%I:%M %p").lstrip("0")
    date_label = start.strftime("%A, %b %d")

    left, sep, right = split_teams(name)
    if not left or not sep or not right:
        continue

    clean_left = re.sub(r"\(.*?\)", "", left).strip()
    clean_right = re.sub(r"\(.*?\)", "", right).strip()

    left_is_hay = is_holbrook_team(left)
    right_is_hay = is_holbrook_team(right)

    if not (left_is_hay or right_is_hay):
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
    crest = get_local_crest(opponent_clean)

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
        "cancelled": False,
    }

    games_by_day[date_label].append(game)
    if is_home:
        home_games_by_day[date_label].append(game)

    # Index ICS games by both orders for cancellation matching
    raw_left = left.strip()
    raw_right = right.strip()
    key1 = f"{date_label} | {time_str} | {raw_left} | {raw_right}"
    key2 = f"{date_label} | {time_str} | {raw_right} | {raw_left}"
    ics_games[key1] = game
    ics_games[key2] = game

# ---------------------------------------------------------
# MERGE CANCELLATIONS (MARK OR RECONSTRUCT)
# ---------------------------------------------------------

for key, info in cancellations.items():

    # If ICS already has this game, just mark it cancelled
    if key in ics_games:
        game = ics_games[key]
        game["cancelled"] = True

        # ALSO update the version stored in games_by_day
        for g in games_by_day.get(info["date"], []):
            # Same date AND same time AND same teams (order doesn't matter)
            if g["time"] == info["time"]:
                if (
                    strip_score_suffix(g["team"]) in [info["home"], info["away"]] or
                    strip_score_suffix(g["opponent"]) in [info["home"], info["away"]]
                ):
                    g["cancelled"] = True

        continue

    # Otherwise, reconstruct the cancelled game
    date_label = info["date"]
    time_str = info["time"]
    home = info["home"]
    away = info["away"]

    # Reconstruct datetime and filter to this week
    try:
        dt = datetime.strptime(f"{date_label} {time_str}", "%A, %b %d %I:%M %p")
        dt = pytz.timezone("US/Eastern").localize(dt)
    except Exception:
        continue

    if not (this_monday.date() <= dt.date() <= this_sunday.date()):
        continue

    left_is_hay = is_holbrook_team(home)
    right_is_hay = is_holbrook_team(away)

    if not (left_is_hay or right_is_hay):
        continue

    if left_is_hay:
        hay_team = home
        opponent = away
        is_home = True
    else:
        hay_team = away
        opponent = home
        is_home = False

    opponent_clean = opponent.strip().upper()
    crest = get_local_crest(opponent_clean)

    game = {
        "team": hay_team,
        "opponent": opponent_clean,
        "opponent_display": ("vs. " + opponent_clean) if is_home else ("@ " + opponent_clean),
        "location": "",
        "normalized_location": "",
        "time": time_str,
        "time_str": time_str,
        "start_dt": dt,
        "is_home": is_home,
        "crest": crest,
        "cancelled": True,
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
    # Holbrook is ALWAYS the "home" side in the HTML grid
    home_team = g["team"]
    home_crest = hayasa_crest

    away_team = g["opponent"]
    away_crest = g["crest"]

    home_crest_html = (
        f"<img class='crest home-crest' src='{home_crest}'>"
        if home_crest else "<span class='crest placeholder'></span>"
    )

    away_crest_html = (
        f"<img class='crest away-crest' src='{away_crest}'>"
        if away_crest else "<span class='crest placeholder'></span>"
    )

    loc_slug = re.sub(r'[^a-z0-9]+', '-', g['normalized_location'].lower()).strip('-')

    return (
        "<div class='game {cls}{cancelled_cls} loc-{loc}'>"
        "<span class='time'>{time}</span>"
        "{home_crest}"
        "<span class='team home-team'>{home_team}</span>"
        "<span class='opponent'>vs.</span>"
        "{away_crest}"
        "<span class='team away-team'>{away_team}</span>"
        "<span class='location'>{loc_name}</span>"
        "{cancel_badge}"
        "</div>"
    ).format(
        cls=home_or_away,
        cancelled_cls=" cancelled" if g.get("cancelled") else "",
        loc=loc_slug,
        time=g["time_str"],
        home_crest=home_crest_html,
        home_team=home_team,
        away_crest=away_crest_html,
        away_team=away_team,
        loc_name=g["normalized_location"],
        cancel_badge="<span class='badge cancelled'>Cancelled</span>" if g.get("cancelled") else "",
    )

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
    html = [html_header("Holbrook Avon Youth Soccer Travel Home Games")]
    html.append('<p class="subtitle">These games are happening right here in Holbrook & Avon.</p>')

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
    html = [html_header("Holbrook Avon Youth Soccer Travel Games")]
    html.append('<p class="subtitle">All Holbrook Avon Youth Soccer travel games this week — home and away.</p>')

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
