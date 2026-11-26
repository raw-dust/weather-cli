#!/usr/bin/env python3
"""Hourly weather in the terminal: `nws` (US National Weather Service) and
`open-meteo` (worldwide). Run either with -h for options and examples."""
import argparse
import ast
import concurrent.futures
import difflib
import datetime as dt
import json
import math
import operator
import os
import re
import tempfile
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_ZIP = "32277"   # US ZIP code used when no location and no default favorite is set
UA = "weather-cli"
APP_DIR_NAME = "weather-cli"      # folder name under the config and cache locations
# $WEATHER_UA (e.g. "weather-cli (Jane Doe, jane@example.com)") is a contact-bearing
# User-Agent. It is sent only to the US agencies that ask for one, never to third parties.
CONTACT_UA_HOSTS = ("api.weather.gov", "tidesandcurrents.noaa.gov")
COMMANDS = ("nws", "open-meteo")   # names the script answers to

# column selection ("cond" is always drawn last so emoji width can't shift others)
ALL_COLUMNS = ["date", "time", "temp", "feels", "rain", "cloud", "wind", "hum", "cond"]
DEFAULT_COLUMNS = "date,time,temp,feels,rain,cond"   # cloud, wind and humidity hidden by default
COLUMN_HELP = {
    "date": "mm/dd/yyyy, shown on the first row of each day",
    "time": "12-hour time",
    "temp": "temperature, °F",
    "feels": "feels-like °F (heat index / wind chill); only when 3° or more off",
    "rain": "chance of rain, %",
    "cloud": "sky cover, % (0 clear, 100 overcast)",
    "wind": "wind direction, speed in mph, (gust)",
    "hum": "relative humidity, %",
    "cond": "emoji and conditions text; always shown last",
}
COLUMN_ALIASES = {"clouds": "cloud", "cover": "cloud", "skycover": "cloud", "humidity": "hum", "conditions": "cond", "condition": "cond",
                  "weather": "cond", "feel": "feels", "precip": "rain",
                  "day": "date"}


def parse_columns(spec):
    """'temp,rain' -> exact list; '+wind' / '-rain' -> change the default; 'all'."""
    base = [c for c in (os.environ.get("WEATHER_COLUMNS") or DEFAULT_COLUMNS).split(",") if c]
    toks = [t.strip().lower() for t in spec.split(",") if t.strip()]
    if not toks:
        sys.exit("--columns needs a list, e.g. --columns temp,rain,cond")

    def clean(t):
        name = t.lstrip("+-")
        return COLUMN_ALIASES.get(name, name)

    for t in toks:
        if clean(t) not in ALL_COLUMNS + ["all"]:
            sys.exit(f"Unknown column '{t.lstrip('+-')}'. Choose from: {' '.join(ALL_COLUMNS)} (or all)")
    if all(t[0] in "+-" for t in toks):          # modify the default set
        chosen = set(base)
        for t in toks:
            (chosen.add if t[0] == "+" else chosen.discard)(clean(t))
        return [c for c in ALL_COLUMNS if c in chosen]
    out = []                                     # explicit list, user's order
    for t in toks:
        for c in (ALL_COLUMNS if clean(t) == "all" else [clean(t)]):
            if c not in out:
                out.append(c)
    return out


COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
           "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]

# WMO weather code -> (text, day icon, night icon)
WMO = {0: ("Clear", "☀️", "🌙"), 1: ("Mostly clear", "🌤️", "🌙"),
       2: ("Partly cloudy", "⛅", "☁️"), 3: ("Overcast", "☁️", "☁️"),
       45: ("Fog", "🌫️", "🌫️"), 48: ("Rime fog", "🌫️", "🌫️"),
       51: ("Light drizzle", "🌦️", "🌧️"), 53: ("Drizzle", "🌦️", "🌧️"),
       55: ("Heavy drizzle", "🌧️", "🌧️"), 61: ("Light rain", "🌦️", "🌧️"),
       63: ("Rain", "🌧️", "🌧️"), 65: ("Heavy rain", "🌧️", "🌧️"),
       66: ("Freezing rain", "🌨️", "🌨️"), 67: ("Freezing rain", "🌨️", "🌨️"),
       71: ("Light snow", "🌨️", "🌨️"), 73: ("Snow", "🌨️", "🌨️"),
       75: ("Heavy snow", "❄️", "❄️"), 77: ("Snow grains", "🌨️", "🌨️"),
       80: ("Light showers", "🌦️", "🌧️"), 81: ("Showers", "🌦️", "🌧️"),
       82: ("Heavy showers", "🌧️", "🌧️"), 85: ("Snow showers", "🌨️", "🌨️"),
       86: ("Snow showers", "🌨️", "🌨️"), 95: ("Thunderstorm", "⛈️", "⛈️"),
       96: ("Thunderstorm, hail", "⛈️", "⛈️"), 99: ("Thunderstorm, hail", "⛈️", "⛈️")}


# ---- colors ---------------------------------------------------------------
def enable_windows_ansi():
    """Turn on ANSI color handling in a Windows console; True if it worked."""
    try:
        import ctypes
        kernel = ctypes.windll.kernel32
        handle = kernel.GetStdHandle(-11)                     # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if not kernel.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(kernel.SetConsoleMode(handle, mode.value | 0x0004))   # VT processing
    except Exception:
        return False


def color_enabled():
    force = os.environ.get("FORCE_COLOR", "")
    if force and force != "0":
        if os.name == "nt":
            enable_windows_ansi()
        return True
    if os.environ.get("NO_COLOR") is not None:
        return False
    if not sys.stdout.isatty():
        return False
    return enable_windows_ansi() if os.name == "nt" else True


COLOR = color_enabled()


def paint(text, code=None, bold=False):
    """Wrap text in an ANSI 256-color code (no-op when color is disabled)."""
    if not COLOR or (code is None and not bold):
        return text
    seq = ("1;" if bold else "") + (f"38;5;{code}" if code is not None else "")
    return f"\033[{seq.rstrip(';')}m{text}\033[0m"


def scale(value, steps):
    """steps: [(upper_bound_exclusive, color), ...]; last color is the default."""
    for bound, c in steps[:-1]:
        if value < bound:
            return c
    return steps[-1][1]


# value -> 256-color code; tune the thresholds here
TEMP_COLOR = [(33, 33), (50, 45), (65, 220), (80, 41), (90, 208), (999, 196)]
RAIN_COLOR = [(20, 244), (50, 117), (80, 39), (999, 33)]
WIND_COLOR = [(10, 41), (20, 220), (30, 208), (999, 196)]
HUM_COLOR = [(30, 220), (60, 41), (80, 45), (999, 33)]
CLOUD_COLOR = [(20, 39), (40, 75), (60, 110), (80, 248), (999, 244)]   # clear blue -> overcast gray
FEELS_MIN_DIFF = 3   # show "Feels" only when it differs from Temp by this many degrees


OPERATORS = {ast.Add: operator.add, ast.Sub: operator.sub,
             ast.Mult: operator.mul, ast.Div: operator.truediv}


def whole_number(text):
    """Option value such as '48', '24*7', '24x7' or '(2+1)*24' -> positive int.
    Only numbers, + - * / and parentheses are evaluated (no eval)."""
    def value(node):
        if isinstance(node, ast.BinOp) and type(node.op) in OPERATORS:
            return OPERATORS[type(node.op)](value(node.left), value(node.right))
        # Python 3.8+ stores the number in .value, 3.7 in .n
        number = node.value if hasattr(node, "value") else getattr(node, "n", None)
        if type(number) is int:
            return number
        raise ValueError

    try:
        if len(text) > 50:
            raise ValueError
        result = value(ast.parse(re.sub("[xX]", "*", text.strip()), mode="eval").body)
        if result < 1 or result != int(result):
            raise ValueError
    except (ValueError, SyntaxError, ZeroDivisionError):
        raise argparse.ArgumentTypeError(
            f"'{text}' is not a positive whole number or sum such as 48 or 24x7")
    return int(result)


def render(title, rows, columns, info=None):
    """Print rows (list of dicts) as a colored table with a header row."""
    if not rows:
        sys.exit("No forecast data returned")
    for r in rows:   # only show "feels like" when it meaningfully differs
        f = r.get("feels")
        if f is None or r["temp"] is None or abs(f - r["temp"]) < FEELS_MIN_DIFF:
            r["feels"] = None

    def num_cells(key, colors):
        return [("-" if r[key] is None else str(r[key]),
                 r[key] is not None and scale(r[key], colors), False) for r in rows]

    def wind_text(r):
        if r["wind"] is None:
            return "-"
        txt = f"{r['wdir'] or '':>3} {r['wind']:>2}"
        return txt + (f" (g{r['gust']})" if r["gust"] else "")

    prev_day, dates = None, []
    for r in rows:
        day = r["time"].date()
        dates.append((r["time"].strftime("%m/%d/%Y") if day != prev_day else "", None, True))
        prev_day = day

    # name -> (header, alignment, cells[(text, color, bold)]) or None if no data
    builders = {
        "date": lambda: ("Date", "<", dates),
        "time": lambda: ("Time", ">", [(t12(r["time"]), None, False) for r in rows]),
        "temp": lambda: ("Temp °F", ">", num_cells("temp", TEMP_COLOR)),
        "feels": lambda: ("Feels °F", ">", [
            ("" if r["feels"] is None else str(r["feels"]),
             r["feels"] is not None and scale(r["feels"], TEMP_COLOR), False)
            for r in rows]) if any(r["feels"] is not None for r in rows) else None,
        "rain": lambda: ("Rain %", ">", num_cells("rain", RAIN_COLOR)),
        "wind": lambda: ("Wind mph", "<", [
            (wind_text(r), r["wind"] is not None and scale(r["wind"], WIND_COLOR), False)
            for r in rows]),
        "cloud": lambda: ("Cloud %", ">", num_cells("cloud", CLOUD_COLOR)),
        "hum": lambda: ("Hum %", ">", num_cells("hum", HUM_COLOR))
            if any(r["hum"] is not None for r in rows) else None,
    }
    cols = [b for b in (builders[c]() for c in columns if c in builders) if b]
    widths = [max(len(h), *(len(c[0]) for c in cells)) for h, _, cells in cols]
    with_cond = "cond" in columns
    cond_head = "Conditions"

    def fmt(text, width, align):
        return f"{text:{align}{width}}"

    print(paint(title, bold=True))
    for line in (info or "").splitlines():
        print(paint(line, 245))
    print()
    print("  ".join([paint(fmt(h, w, a), bold=True) for (h, a, _), w in zip(cols, widths)]
                    + ([paint(cond_head, bold=True)] if with_cond else [])))
    print("  ".join(["─" * w for w in widths] + (["─" * len(cond_head)] if with_cond else [])))
    for i, r in enumerate(rows):
        parts = []
        for (h, a, cells), w in zip(cols, widths):
            text, code, bold = cells[i]
            parts.append(paint(fmt(text, w, a), code or None, bold))
        # icon + text is the last column and left unpadded, so emoji width
        # differences between terminals cannot shift any other column
        if with_cond:
            mark = (f"   {paint(r['tide'], 117)}" if r.get("tide") else "") \
                + (f"   {paint(r['sun'], 220)}" if r.get("sun") else "")
            parts.append(f"{r['icon']} {r['cond']}{mark}")
        print("  ".join(parts))


def fetch(url, params=None, missing_ok=False, fatal=True, headers=None, retries=0):
    """GET a URL and return the body bytes. Server errors and network failures
    are retried `retries` times; 404 returns b"{}" when missing_ok."""
    if params:
        url += "?" + urllib.parse.urlencode(params)
    host = urllib.parse.urlsplit(url).hostname or ""
    agent = os.environ.get("WEATHER_UA", "").strip() if host.endswith(CONTACT_UA_HOSTS) else ""
    req = urllib.request.Request(url, headers=dict(headers or {}, **{"User-Agent": agent or UA}))
    error = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if missing_ok and e.code == 404:
                return b"{}"
            error = e
            try:   # APIs usually explain a 4xx in a small JSON body
                body = json.loads(e.read().decode("utf-8", "replace"))
                detail = body.get("reason") or body.get("detail") or body.get("title")
                if detail:
                    error = f"{e} ({detail})"
            except (ValueError, AttributeError, OSError):
                pass
            if e.code < 500:
                break
        except OSError as e:
            error = e
        if attempt < retries:
            time.sleep(1 + attempt)
    if not fatal:
        return None
    sys.exit(f"Request failed: {error}")


def is_zip(s):
    return len(s) == 5 and s.isdigit()


def zip_lookup(z):
    """US ZIP code -> (lat, lon, "City, ST") via zippopotam.us."""
    try:
        data = json.loads(fetch(f"https://api.zippopotam.us/us/{z}", missing_ok=True))
        p = data["places"][0]
        return (float(p["latitude"]), float(p["longitude"]),
                f"{p['place name']}, {p['state abbreviation']}")
    except (ValueError, KeyError, IndexError, json.JSONDecodeError):
        sys.exit(f"ZIP code not found: {z}")


def t12(t):
    return f"{t.hour % 12 or 12:2d} {'AM' if t.hour < 12 else 'PM'}"


def clock(t):
    """12-hour clock without padding: 6:55 AM"""
    return f"{t.hour % 12 or 12}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def sun_times(day, lat, lon, tz, altitude=-0.833):
    """Sunrise/sunset for a date (NOAA sunrise equation, no network).

    `altitude` is the sun's center in degrees: -0.833 for sunrise and sunset,
    -6 / -12 / -18 for civil / nautical / astronomical twilight.
    Returns (sunrise, sunset) as aware datetimes in tz, or ("day", None) when
    the sun never sets / ("night", None) when it never rises (polar regions)."""
    rad = math.radians
    n = (day - dt.date(2000, 1, 1)).days
    jstar = n - lon / 360.0                          # mean solar noon (lon: east +)
    m = (357.5291 + 0.98560028 * jstar) % 360
    c = 1.9148 * math.sin(rad(m)) + 0.02 * math.sin(rad(2 * m)) + 0.0003 * math.sin(rad(3 * m))
    lam = (m + c + 180 + 102.9372) % 360
    transit = jstar + 0.0053 * math.sin(rad(m)) - 0.0069 * math.sin(rad(2 * lam))
    sin_dec = math.sin(rad(lam)) * math.sin(rad(23.4397))
    cos_dec = math.sqrt(1 - sin_dec ** 2)
    cos_h = ((math.sin(rad(altitude)) - math.sin(rad(lat)) * sin_dec)
             / (math.cos(rad(lat)) * cos_dec))
    if cos_h > 1:
        return "night", None
    if cos_h < -1:
        return "day", None
    h = math.degrees(math.acos(cos_h))
    epoch = dt.datetime(2000, 1, 1, 12, tzinfo=dt.timezone.utc)
    rise = epoch + dt.timedelta(days=transit - h / 360.0)
    sset = epoch + dt.timedelta(days=transit + h / 360.0)
    return rise.astimezone(tz), sset.astimezone(tz)


TWILIGHT = {"civil": -6, "nautical": -12, "astronomical": -18}   # sun's center, degrees


def twilight_times(day, lat, lon, tz, kind="civil"):
    """(dawn, dusk): when the sun reaches the twilight angle on the way up and
    down. (None, None) when it never does that day (polar summer or winter)."""
    a, b = sun_times(day, lat, lon, tz, TWILIGHT[kind])
    return (None, None) if isinstance(a, str) else (a, b)


def _moon_altitude(when, lat, lon):
    """Altitude (radians) of the moon's center at an aware datetime.

    Low-precision lunar position (the SunCalc approximation); good to a few
    minutes for rise/set times."""
    rad = math.radians
    d = (when - dt.datetime(2000, 1, 1, 12, tzinfo=dt.timezone.utc)).total_seconds() / 86400.0
    lon_ecl = rad(218.316 + 13.176396 * d) + rad(6.289) * math.sin(rad(134.963 + 13.064993 * d))
    lat_ecl = rad(5.128) * math.sin(rad(93.272 + 13.229350 * d))
    e = rad(23.4397)
    ra = math.atan2(math.sin(lon_ecl) * math.cos(e) - math.tan(lat_ecl) * math.sin(e),
                    math.cos(lon_ecl))
    dec = math.asin(math.sin(lat_ecl) * math.cos(e)
                    + math.cos(lat_ecl) * math.sin(e) * math.sin(lon_ecl))
    hour_angle = rad(280.16 + 360.9856235 * d) + rad(lon) - ra
    phi = rad(lat)
    h = math.asin(math.sin(phi) * math.sin(dec)
                  + math.cos(phi) * math.cos(dec) * math.cos(hour_angle))
    h0 = max(h, 0)
    return h + 0.0002967 / math.tan(h0 + 0.00312536 / (h0 + 0.08901179))


def moon_times(day, lat, lon, tz):
    """(moonrise, moonset) on a local calendar day, either may be None
    (the moon rises about 50 minutes later each day, so some days have none)."""
    hc = math.radians(0.133)   # refraction + parallax + semi-diameter allowance
    start = dt.datetime(day.year, day.month, day.day, tzinfo=tz)
    alt = lambda hours: _moon_altitude(start + dt.timedelta(hours=hours), lat, lon) - hc
    rise = sset = None
    h0 = alt(0)
    for i in range(1, 25, 2):
        h1, h2 = alt(i), alt(i + 1)
        a, b = (h0 + h2) / 2 - h1, (h2 - h0) / 2
        if a != 0:
            xe = -b / (2 * a)
            ye = (a * xe + b) * xe + h1
            disc = b * b - 4 * a * h1
            roots = 0
            if disc >= 0:
                dx = math.sqrt(disc) / (abs(a) * 2)
                x1, x2 = xe - dx, xe + dx
                roots = (abs(x1) <= 1) + (abs(x2) <= 1)
                if x1 < -1:
                    x1 = x2
            if roots == 1:
                if h0 < 0:
                    rise = i + x1
                else:
                    sset = i + x1
            elif roots == 2:
                rise = i + (x2 if ye < 0 else x1)
                sset = i + (x1 if ye < 0 else x2)
        if rise is not None and sset is not None:
            break
        h0 = h2
    at = lambda hours: None if hours is None else start + dt.timedelta(hours=hours)
    return at(rise), at(sset)


MOON_PHASES = [(0.03, "🌑", "New moon"), (0.22, "🌒", "Waxing crescent"),
               (0.28, "🌓", "First quarter"), (0.47, "🌔", "Waxing gibbous"),
               (0.53, "🌕", "Full moon"), (0.72, "🌖", "Waning gibbous"),
               (0.78, "🌗", "Last quarter"), (0.97, "🌘", "Waning crescent"),
               (1.01, "🌑", "New moon")]


def moon_phase(day):
    """(emoji, name, percent illuminated) for a date; accurate to about a day."""
    synodic = 29.530588853
    new_moon = dt.datetime(2000, 1, 6, 18, 14)       # a known new moon (UTC)
    age = ((dt.datetime(day.year, day.month, day.day, 12) - new_moon).total_seconds()
           / 86400.0) % synodic
    frac = age / synodic
    pct = round((1 - math.cos(2 * math.pi * frac)) / 2 * 100)
    for bound, emoji, name in MOON_PHASES:
        if frac < bound:
            return emoji, name, pct


TIDE_RADIUS_MILES = 25   # no tide line if no NOAA station is this close
TIDE_STATIONS_URL = "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations.json"
TIDE_DATA_URL = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"


def miles_between(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 3958.8 * 2 * math.asin(math.sqrt(a))


def cache_dir():
    """Per-user cache folder: XDG on Linux, ~/Library/Caches on macOS, %LOCALAPPDATA% on Windows."""
    if os.environ.get("XDG_CACHE_HOME"):
        base = Path(os.environ["XDG_CACHE_HOME"])
    elif sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path.home() / ".cache"
    return base / APP_DIR_NAME


def tide_stations():
    """NOAA tide-prediction stations, cached on disk for 30 days."""
    cache = cache_dir() / "tide-stations.json"
    try:
        if time.time() - cache.stat().st_mtime < 30 * 86400:
            return json.loads(cache.read_text())
    except (OSError, ValueError):
        pass
    body = fetch(TIDE_STATIONS_URL, {"type": "tidepredictions"}, fatal=False)
    try:
        stations = [{"id": x["id"], "name": x["name"], "state": x.get("state", ""),
                     "lat": x["lat"], "lng": x["lng"]}
                    for x in json.loads(body)["stations"]]
    except (TypeError, ValueError, KeyError):
        return []
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(stations))
    except OSError:
        pass
    return stations


def add_tides(rows, lat, lon):
    """Flag the hour of each high/low tide on the rows (row["tide"]) and return
    the first-day summary line, or None when there is no NOAA station nearby
    or NOAA can't be reached."""
    if not rows:
        return None
    best = min(((miles_between(lat, lon, st["lat"], st["lng"]), st)
                for st in tide_stations()), default=None, key=lambda x: x[0])
    if best is None or best[0] > TIDE_RADIUS_MILES:
        return None
    miles, st = best
    first, last = rows[0]["time"].date(), rows[-1]["time"].date()
    body = fetch(TIDE_DATA_URL, {
        "product": "predictions", "application": "weather-cli", "datum": "MLLW",
        "station": st["id"], "begin_date": f"{first:%Y%m%d}", "end_date": f"{last:%Y%m%d}",
        "time_zone": "lst_ldt", "units": "english", "interval": "hilo",
        "format": "json"}, fatal=False)
    try:
        events = json.loads(body)["predictions"]
    except (TypeError, ValueError, KeyError):
        return None
    by_hour, parts = {}, []
    for e in events:
        t = dt.datetime.strptime(e["t"], "%Y-%m-%d %H:%M")
        kind = "High" if e["type"] == "H" else "Low"
        by_hour.setdefault(t.strftime("%Y-%m-%dT%H"), []).append(f"🌊 {kind[0]} {clock(t)}")   # H / L
        if t.date() == first:   # the summary line keeps the heights
            parts.append(f"{kind} {clock(t)} {float(e['v']):.1f} ft")
    for r in rows:   # the row whose hour contains the tide gets the marker
        r["tide"] = "   ".join(by_hour.get(r["time"].strftime("%Y-%m-%dT%H"), [])) or None
    if not parts:
        return None
    name = st["name"].title() if st["name"].isupper() else st["name"]
    where = f"{name}{', ' + st['state'] if st['state'] else ''}, {miles:.0f} mi"
    line = "🌊 " + "  ·  ".join(parts)
    cols = shutil.get_terminal_size((100, 24)).columns
    return line + f"  ·  {where}" if len(line) + len(where) + 6 <= cols else f"{line}\n    ({where})"


TWILIGHT_LABELS = {"civil": ("Dawn", "Dusk"), "nautical": ("Nautical dawn", "Nautical dusk"),
                   "astronomical": ("Astro dawn", "Astro dusk")}


def sky_line(day, sunrise, sunset, state="normal", moonrise=None, moonset=None,
             dawn=None, dusk=None, kind="civil"):
    """Two info lines: sun times (with twilight), then moonrise, moonset and moon phase."""
    if state == "day":
        sun = "🌞 Sun up all day"
    elif state == "night":
        sun = "🌑 Sun down all day"
    else:
        names = TWILIGHT_LABELS.get(kind, TWILIGHT_LABELS["civil"])   # "none" has no dawn/dusk to label
        parts = ([f"🌄 {names[0]} {clock(dawn)}"] if dawn else []) + [
            f"🌅 Sunrise {clock(sunrise)}", f"🌇 Sunset {clock(sunset)}"] + (
            [f"🌆 {names[1]} {clock(dusk)}"] if dusk else [])
        sun = "  ·  ".join(parts)
    emoji, name, pct = moon_phase(day)
    when = lambda t: clock(t) if t else "none"
    moon = (f"⬆ Moonrise {when(moonrise)}  ·  ⬇ Moonset {when(moonset)}"
            f"  ·  {emoji} {name} ({pct}%)")
    return sun + "\n" + moon


NWS_API = "https://api.weather.gov"
NWS_HEADERS = {"Accept": "application/geo+json"}


def parse_duration(text):
    """ISO 8601 duration such as PT1H, PT5H or P7DT8H -> whole hours."""
    m = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?", text)
    if not m:
        return 1
    d, h, mi = (int(x or 0) for x in m.groups())
    return max(1, d * 24 + h + mi // 60)


def expand_series(series):
    """NWS grid values come as {"validTime": "start/PT5H", "value": v} spans.
    Return {utc_hour_number: value} with one entry per hour of every span."""
    out = {}
    for item in (series or {}).get("values", []):
        if item.get("value") is None:
            continue
        start, _, length = item["validTime"].partition("/")
        first = int(dt.datetime.fromisoformat(start).timestamp() // 3600)
        for k in range(min(parse_duration(length), 24 * 8)):
            out[first + k] = item["value"]
    return out


def forecast_icon(text, day):
    """Emoji for an NWS short forecast such as 'Chance Rain Showers'."""
    t = text.lower()
    if "thunder" in t:
        return "⛈️"
    if any(w in t for w in ("snow", "sleet", "flurr", "ice", "freezing", "wintry")):
        return "🌨️"
    if any(w in t for w in ("fog", "haze", "smoke", "mist")):
        return "🌫️"
    if any(w in t for w in ("rain", "shower", "drizzle")):
        return "🌧️" if any(w in t for w in ("likely", "heavy")) or t.strip() == "rain" else "🌦️"
    if "partly" in t:
        return "⛅" if day else "☁️"
    if "sunny" in t or "clear" in t:
        if "mostly" in t:
            return "🌤️" if day else "🌙"
        return "☀️" if day else "🌙"
    return "☁️"


def nws(hours, lat, lon, columns, sky=True, tides=True, fav=None, twilight="civil"):
    lat, lon = round(lat, 4), round(lon, 4)   # the API wants at most 4 decimals
    point = json.loads(fetch(f"{NWS_API}/points/{lat},{lon}", headers=NWS_HEADERS,
                             missing_ok=True, retries=2))
    props = point.get("properties")
    if not props:
        sys.exit("The NWS has no forecast for that location (it covers the US and its territories).")

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        hourly_job = pool.submit(fetch, props["forecastHourly"], {"units": "us"},
                                 headers=NWS_HEADERS, retries=2)
        grid_job = pool.submit(fetch, props["forecastGridData"],
                               headers=NWS_HEADERS, fatal=False, retries=2)
        hourly_body, grid_body = hourly_job.result(), grid_job.result()
    periods = json.loads(hourly_body)["properties"]["periods"]
    try:   # the grid adds sky cover, gusts and feels-like; the table works without it
        grid = json.loads(grid_body)["properties"]
    except (TypeError, ValueError, KeyError):
        grid = {}
    cloud = expand_series(grid.get("skyCover"))
    gust = expand_series(grid.get("windGust"))                # km/h
    apparent = expand_series(grid.get("apparentTemperature"))  # °C: heat index or wind chill

    rel = props.get("relativeLocation", {}).get("properties", {})
    place = (f"{rel['city']}, {rel['state']}" if rel.get("city") else f"{lat}, {lon}")
    place += f" · NWS grid {props['gridId']} {props['gridX']},{props['gridY']}"

    sun_cache = {}

    def sun_for(d, tz):   # the API has no sunrise data, so compute it
        if d not in sun_cache:
            sun_cache[d] = sun_times(d, lat, lon, tz)
        return sun_cache[d]

    def sun_marker(t):   # "🌅 6:55 AM" on the row whose hour contains sunrise/sunset
        if not sky:
            return None
        a, b = sun_for(t.date(), t.tzinfo)
        if a in ("day", "night"):
            return None
        for icon, ev in (("🌅", a), ("🌇", b)):
            if ev.replace(minute=0, second=0, microsecond=0) == t.replace(minute=0, second=0, microsecond=0):
                return f"{icon} {clock(ev)}"
        return None

    def value(field):
        return (field or {}).get("value")

    rows = []
    first_time = dt.datetime.fromisoformat(periods[0]["startTime"])
    now = dt.datetime.now(first_time.tzinfo).replace(minute=0, second=0, microsecond=0)
    for p in periods:
        t = dt.datetime.fromisoformat(p["startTime"])
        if t < now:
            continue
        if len(rows) >= hours:
            break
        key = int(t.timestamp() // 3600)
        speeds = re.findall(r"\d+", p.get("windSpeed") or "")
        speed = int(speeds[-1]) if speeds else None
        g = gust.get(key)
        g = round(g / 1.609344) if g is not None else None
        feels = apparent.get(key)
        text = p.get("shortForecast") or "?"
        rows.append({"time": t, "temp": p.get("temperature"),
                     "feels": round(feels * 9 / 5 + 32) if feels is not None else None,
                     "rain": value(p.get("probabilityOfPrecipitation")),
                     "wdir": p.get("windDirection") or "", "wind": speed,
                     "gust": g if g is not None and speed is not None and g - speed >= 5 else None,
                     "hum": value(p.get("relativeHumidity")),
                     "cloud": round(cloud[key]) if key in cloud else None,
                     "icon": forecast_icon(text, p.get("isDaytime", True)),
                     "cond": text.capitalize(), "sun": sun_marker(t)})
    info = None
    if sky:
        first = rows[0]["time"] if rows else now
        rise, sset = sun_times(first.date(), lat, lon, first.tzinfo)
        mrise, mset = moon_times(first.date(), lat, lon, first.tzinfo)
        dawn, dusk = (twilight_times(first.date(), lat, lon, first.tzinfo, twilight)
                      if twilight in TWILIGHT else (None, None))
        info = (sky_line(first.date(), None, None, rise, mrise, mset) if rise in ("day", "night")
                else sky_line(first.date(), rise, sset, "normal", mrise, mset, dawn, dusk, twilight))
    if tides:
        tl = add_tides(rows, lat, lon)
        info = "\n".join(x for x in (info, tl) if x) or None
    render("NWS hourly forecast: " + place + (f" · ★ {fav}" if fav else ""), rows, columns, info)


def open_meteo(hours, lat, lon, label, columns, sky=True, tides=True, fav=None, model=None,
               twilight="civil"):
    params = {
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m",
        "hourly": "temperature_2m,precipitation_probability,weather_code,"
                  "wind_speed_10m,wind_direction_10m,wind_gusts_10m,"
                  "relative_humidity_2m,apparent_temperature,cloud_cover,is_day",
        "temperature_unit": "fahrenheit", "wind_speed_unit": "mph",
        "daily": "sunrise,sunset",
        "timezone": "auto",
        # enough days for the hours asked (today is partly over); 16 is the API maximum
        "forecast_days": min(16, max(3, (hours + 47) // 24))}
    if model:
        params["models"] = model
    try:
        data = json.loads(fetch("https://api.open-meteo.com/v1/forecast", params))
    except SystemExit as e:
        if model and "Invalid value" in str(e.code):
            sys.exit(f"Open-Meteo doesn't know the model '{model}'. Run open-meteo -h "
                     "for the model list.")
        raise
    h = data["hourly"]

    def val(key, i):   # some models leave a variable empty or end early
        series = h.get(key)
        return series[i] if series and i < len(series) else None

    now = data["current"]["time"][:13]
    marks = {}   # local hour -> "🌅 6:55 AM"
    if sky:
        for k, d in enumerate(data["daily"]["time"]):
            for key, icon in (("sunrise", "🌅"), ("sunset", "🌇")):
                v = data["daily"][key][k]
                if v and data["daily"]["sunrise"][k] and data["daily"]["sunrise"][k] < (data["daily"]["sunset"][k] or ""):
                    ev = dt.datetime.fromisoformat(v)
                    marks[ev.strftime("%Y-%m-%dT%H")] = f"{icon} {clock(ev)}"
    rows = []
    for i in [i for i, s in enumerate(h["time"]) if s[:13] >= now][:hours]:
        temp = val("temperature_2m", i)
        if temp is None:   # this model's forecast ends here
            break
        text, day_icon, night_icon = WMO.get(val("weather_code", i), ("?", "❔", "❔"))
        d, g, w, feels = (val("wind_direction_10m", i), val("wind_gusts_10m", i),
                          val("wind_speed_10m", i), val("apparent_temperature", i))
        w = round(w) if w is not None else None
        rows.append({"time": dt.datetime.fromisoformat(h["time"][i]),
                     "temp": round(temp),
                     "feels": round(feels) if feels is not None else None,
                     "rain": val("precipitation_probability", i),
                     "wdir": COMPASS[round(d / 22.5) % 16] if d is not None else "",
                     "wind": w,
                     "gust": round(g) if g is not None and w is not None and round(g) - w >= 5 else None,
                     "hum": val("relative_humidity_2m", i),
                     "cloud": val("cloud_cover", i),
                     "icon": night_icon if val("is_day", i) == 0 else day_icon,
                     "cond": text, "sun": marks.get(h["time"][i][:13])})
    if not rows:
        sys.exit(f"Open-Meteo returned no forecast hours{' for model ' + model if model else ''}.")
    info = None
    if sky:
        first = rows[0]["time"].date() if rows else dt.date.today()
        day = data["daily"]
        k = day["time"].index(first.isoformat()) if first.isoformat() in day["time"] else 0
        rise = dt.datetime.fromisoformat(day["sunrise"][k]) if day["sunrise"][k] else None
        sset = dt.datetime.fromisoformat(day["sunset"][k]) if day["sunset"][k] else None
        tz = dt.timezone(dt.timedelta(seconds=data["utc_offset_seconds"]))
        mrise, mset = moon_times(first, lat, lon, tz)
        if rise and sset and rise < sset:
            dawn, dusk = (twilight_times(first, lat, lon, tz, twilight)
                          if twilight in TWILIGHT else (None, None))
            info = sky_line(first, rise, sset, "normal", mrise, mset, dawn, dusk, twilight)
        else:   # polar day/night: no real sunrise or sunset that day
            up = any(val("is_day", i) for i, s in enumerate(h["time"]) if s[:10] == first.isoformat())
            info = sky_line(first, None, None, "day" if up else "night", mrise, mset)
    if tides:
        tl = add_tides(rows, lat, lon)
        info = "\n".join(x for x in (info, tl) if x) or None
    render(f"Open-Meteo hourly forecast: {label} · {lat:.2f}, {lon:.2f}"
           + (f" · model {model}" if model else "") + (f" · ★ {fav}" if fav else ""),
           rows, columns, info)


MODEL_GROUPS = {   # coverage -> {name: description}, as offered on open-meteo.com/en/docs
    "Default": {
        "best_match": "automatic choice for the location (the default)",
    },
    "Worldwide": {
        "ecmwf_ifs": "ECMWF IFS HRES 9km",
        "ecmwf_ifs025": "ECMWF IFS 0.25°",
        "ecmwf_aifs025_single": "ECMWF AIFS 0.25° Single",
        "cma_grapes_global": "CMA GRAPES Global",
        "ncep_gfs_seamless": "NCEP GFS Seamless",
        "ncep_gfs_global": "NCEP GFS Global 0.11°/0.25°",
        "ncep_aigfs025": "NCEP AIGFS 0.25°",
        "ncep_hgefs025_ensemble_mean": "NCEP HGEFS 0.25° Ensemble Mean",
        "jma_seamless": "JMA Seamless",
        "jma_gsm": "JMA GSM",
        "dwd_icon_seamless": "DWD ICON Seamless",
        "dwd_icon_global": "DWD ICON Global",
        "dwd_icon_global_native": "DWD ICON Global Native",
        "dwd_aicon_global_native": "DWD AICON Global Native",
        "cmc_gem_seamless": "GEM Seamless",
        "cmc_gem_gdps": "GEM Global",
        "meteofrance_seamless": "Météo-France Seamless",
        "meteofrance_arpege_world": "Météo-France ARPEGE World",
        "metno_seamless": "MET Norway Nordic Seamless (with ECMWF)",
        "knmi_seamless": "KNMI Seamless (with ECMWF)",
        "dmi_seamless": "DMI Seamless (with ECMWF)",
        "ukmo_seamless": "UK Met Office Seamless",
        "ukmo_global_deterministic_10km": "UK Met Office Global 10km",
        "geosphere_seamless": "GeoSphere Seamless (with ECMWF)",
    },
    "North America only": {
        "ncep_rrfs_north_america": "NCEP RRFS North America",
        "ncep_rrfs_conus": "NCEP RRFS U.S. CONUS",
        "ncep_hrrr_conus": "NCEP HRRR U.S. CONUS",
        "ncep_nbm_conus": "NCEP NBM U.S. CONUS",
        "cmc_gem_rdps": "GEM Regional",
        "cmc_gem_hrdps": "GEM HRDPS Continental",
        "cmc_gem_hrdps_west": "GEM HRDPS West",
    },
    "Europe only": {
        "dwd_icon_eu": "DWD ICON EU",
        "dwd_icon_eu_native": "DWD ICON EU Native",
        "dwd_icon_d2": "DWD ICON D2",
        "dwd_icon_d2_native": "DWD ICON D2 Native",
        "dwd_icon_d2_ruc_native": "DWD ICON D2 RUC Native",
        "meteofrance_arpege_europe": "Météo-France ARPEGE Europe",
        "meteofrance_arome_france": "Météo-France AROME France",
        "meteofrance_arome_france_hd": "Météo-France AROME France HD",
        "italia_meteo_arpae_icon_2i": "ItaliaMeteo ARPAE ICON 2I",
        "metno_nordic": "MET Norway Nordic",
        "knmi_harmonie_arome_europe": "KNMI Harmonie AROME Europe",
        "knmi_harmonie_arome_netherlands": "KNMI Harmonie AROME Netherlands",
        "dmi_harmonie_arome_europe": "DMI Harmonie AROME Europe",
        "ukmo_uk_deterministic_2km": "UK Met Office UK 2km",
        "meteoswiss_icon_seamless": "MeteoSwiss ICON Seamless",
        "meteoswiss_icon_ch1": "MeteoSwiss ICON CH1",
        "meteoswiss_icon_ch2": "MeteoSwiss ICON CH2",
        "geosphere_claef_austria": "GeoSphere C-LAEF Austria",
        "chmi_aladin_seamless": "CHMI Aladin Seamless",
        "chmi_aladin_central_europe_2km": "CHMI Aladin Central Europe 2km",
        "chmi_aladin_cz_1km": "CHMI Aladin CZ 1km",
    },
    "Japan only": {
        "jma_msm": "JMA MSM",
    },
}

ABBREVIATIONS = {"st": "Saint", "ft": "Fort", "mt": "Mount", "jax": "Jacksonville", "bch": "Beach"}


def city_queries(text):
    """Spellings to try, best first: 'Jax FL' -> 'Jacksonville, FL', ..."""
    text = " ".join(text.split())
    expanded = re.sub(r"\b(st|ft|mt|jax|bch)\b\.?", lambda m: ABBREVIATIONS[m.group(1).lower()],
                      text, flags=re.IGNORECASE)

    def with_comma(t):   # "Name FL" -> "Name, FL" (the geocoder wants the comma)
        return t if "," in t else re.sub(r"\s+([A-Za-z]{2})$", r", \1", t)

    seen = []
    for q in (with_comma(expanded), expanded, with_comma(text), text):
        if q and q not in seen:
            seen.append(q)
    return seen


def geocode_city(city):
    tried = city_queries(city)
    for query in tried:
        geo = json.loads(fetch("https://geocoding-api.open-meteo.com/v1/search",
                               {"name": query, "count": 1, "format": "json"}))
        if geo.get("results"):
            g = geo["results"][0]
            return (g["latitude"], g["longitude"],
                    f"{g['name']}, {g.get('admin1') or g.get('country')}")
    sys.exit(f"Location not found: {city}\n"
             'Try the full spelling with a comma, for example "Jacksonville, FL", '
             "or use --zip.")


def config_dir():
    """Per-user settings folder: XDG on Linux, Application Support on macOS, %APPDATA% on Windows."""
    if os.environ.get("XDG_CONFIG_HOME"):
        base = Path(os.environ["XDG_CONFIG_HOME"])
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path.home() / ".config"
    return base / APP_DIR_NAME


FAVORITES_FILE = "favorites.json"


def load_favorites():
    """{lowercase name: {"name", "lat", "lon", "label"}}; empty if none or unreadable."""
    path = config_dir() / FAVORITES_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        sys.exit(f"Could not read {path}; fix or delete it.")
    return data if isinstance(data, dict) else {}


def write_json(path, data, what):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")   # write then rename,
        with os.fdopen(fd, "w", encoding="utf-8") as f:                    # so a crash can't
            json.dump(data, f, indent=2, ensure_ascii=False)               # leave a half file
        os.replace(tmp, str(path))
    except OSError as e:
        sys.exit(f"Could not save {what} to {path}: {e}")


def save_favorites(favs):
    write_json(config_dir() / FAVORITES_FILE, favs, "favorites")


SETTINGS_FILE = "settings.json"


def load_settings():
    """Small saved settings (currently just the default favorite); {} if none or unreadable."""
    try:
        data = json.loads((config_dir() / SETTINGS_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def saved_default_key():
    """Lowercase name of the favorite chosen as the default location, if any."""
    key = load_settings().get("default_favorite")
    return key if isinstance(key, str) and key else None


def default_favorite():
    """The favorite to use when no location is given, or None for the built-in ZIP."""
    key = saved_default_key()
    if not key:
        return None
    favs = load_favorites()
    if key in favs:
        return favs[key]
    print(f"warning: default favorite '{key}' no longer exists; using ZIP {DEFAULT_ZIP}. "
          "Fix it with --set-default NAME or --clear-default.", file=sys.stderr)
    return None


def default_description():
    """For the help text: what 'no location given' means right now."""
    key = saved_default_key()
    try:
        favs = json.loads((config_dir() / FAVORITES_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        favs = {}
    if key and isinstance(favs, dict) and key in favs:
        return "favorite %s" % favs[key].get("name", key)
    return "ZIP %s" % DEFAULT_ZIP


def favorite_key(name):
    name = " ".join(name.split())
    if not name or name.startswith("-") or len(name) > 30:
        sys.exit("Favorite names are 1 to 30 characters and can't start with '-'.")
    return name.lower(), name


def get_favorite(name):
    favs = load_favorites()
    key = " ".join(name.split()).lower()
    if key in favs:
        return favs[key]
    close = difflib.get_close_matches(key, list(favs), n=1)
    hint = f" Did you mean '{favs[close[0]]['name']}'?" if close else ""
    have = ", ".join(sorted(f["name"] for f in favs.values())) or "none saved yet"
    sys.exit(f"No favorite named '{name}'.{hint} Favorites: {have}. "
             "Save one with --save-fav NAME.")


def list_favorites():
    favs = load_favorites()
    if not favs:
        print("No favorite locations yet. Save one with, for example:\n"
              "  nws --zip 32202 --save-fav downtown")
        return
    default = saved_default_key()
    names = {k: favs[k]["name"] + (" (default)" if k == default else "") for k in favs}
    width = max(len(n) for n in names.values())
    print(paint("Favorite locations", bold=True))
    for key in sorted(favs):
        f = favs[key]
        print(f"  ★ {names[key]:<{width}}  {f['label']}  ·  {f['lat']:.2f}, {f['lon']:.2f}")
    if not default:
        print(f"\nNo default favorite: with no location given the built-in ZIP {DEFAULT_ZIP} is used.")


def build_parser(name):
    nws_cmd = name == "nws"
    p = argparse.ArgumentParser(
        prog=name, add_help=False, formatter_class=argparse.RawDescriptionHelpFormatter,
        description=("NWS hourly forecast (US only, no API key)." if nws_cmd else
                     "Open-Meteo hourly forecast (worldwide, no API key)."),
        epilog=(EXAMPLES_NWS if nws_cmd else EXAMPLES_OPEN_METEO + models_help()) + favorites_help() + columns_help())
    p.add_argument("-h", "-?", "--help", action="help", help="show this help message and exit")
    where = p.add_argument_group("location (default: %s)" % default_description())
    where.add_argument("-z", "--zip", metavar="ZIP", help="US ZIP code")
    if nws_cmd:
        where.add_argument("--lat", type=float, metavar="DEG", help="latitude (use with --lon)")
        where.add_argument("--lon", type=float, metavar="DEG", help="longitude (use with --lat)")
    else:
        where.add_argument("-C", "--city", metavar="NAME",
                         help='city name, anywhere in the world; add a state like "Jacksonville, FL"')
    where.add_argument("-F", "--fav", metavar="NAME", help="use a saved favorite location")
    fav = p.add_argument_group("favorite locations")
    fav.add_argument("--save-fav", metavar="NAME",
                     help="save the location you give with %s under NAME" %
                     ("--zip or --lat and --lon" if nws_cmd else "--zip or --city"))
    fav.add_argument("--set-default", metavar="NAME",
                     help="make a saved favorite the default location, then exit")
    fav.add_argument("--clear-default", action="store_true",
                     help="go back to the built-in default ZIP %s, then exit" % DEFAULT_ZIP)
    fav.add_argument("--list-favs", action="store_true", help="list saved favorites and exit")
    fav.add_argument("--remove-fav", metavar="NAME", help="delete a saved favorite and exit")
    if not nws_cmd:
        p.add_argument("--model", metavar="NAME",
                       help="weather model to use (default best_match); see \"models\" below")
    p.add_argument("-n", "--hours", type=whole_number, metavar="N",
                   help="hours to show (default 24); can be calculated with + - * / x and "
                        "parentheses, e.g. 24x7 (quote * and parentheses: '24*7')")
    p.add_argument("-c", "--columns", metavar="LIST",
                   help="columns to show, see \"available columns\" below; default %s" % DEFAULT_COLUMNS)
    p.add_argument("-f", "--full", action="store_true",
                   help="show every column (same as --columns all)")
    p.add_argument("--sky", dest="sky", action="store_true", default=None,
                   help="show sun/moon lines and sunrise/sunset markers (default)")
    p.add_argument("--no-sky", dest="sky", action="store_false", help="hide them")
    p.add_argument("--twilight", choices=["civil", "nautical", "astronomical", "none"],
                   help="twilight shown on the sun line: civil (default), nautical, astronomical or none")
    p.add_argument("--tides", dest="tides", action="store_true", default=None,
                   help="show tides near US coasts (default)")
    p.add_argument("--no-tides", dest="tides", action="store_false", help="hide them")
    return p


def models_help():
    lines = ["", "models (--model NAME, or $WEATHER_MODEL):"]
    for group, models in MODEL_GROUPS.items():
        lines.append("  %s:" % group)
        lines += ["    %-32s %s" % item for item in models.items()]
    lines += ["  Regional models only work for locations inside their area. A model may leave",
              "  some columns empty (for example rain chance) or cover fewer hours.", ""]
    return "\n".join(lines) + "\n"

def favorites_help():
    """The 'favorites' block for -h: where they live and which ones exist now."""
    try:
        names = sorted(f["name"] for f in json.loads(
            (config_dir() / FAVORITES_FILE).read_text(encoding="utf-8")).values())
    except (OSError, ValueError, AttributeError, KeyError, TypeError):
        names = []
    saved = ", ".join(names) if names else "none yet"
    return "\n".join([
        "",
        "favorites (-F NAME):",
        "  names ignore case; saved in %s" % (config_dir() / FAVORITES_FILE),
        "  default location: %s  (--set-default NAME, --clear-default)" % default_description(),
        "  saved now: %s" % saved,
        "",
    ])


def columns_help():
    """The 'available columns' block for -h, built from COLUMN_HELP."""
    default = DEFAULT_COLUMNS.split(",")
    lines = ["", "available columns (-c / --columns):"]
    for name in ALL_COLUMNS:
        mark = "" if name in default else "  [off by default]"
        lines.append("  %-6s %s%s" % (name, COLUMN_HELP[name], mark))
    lines += [
        "",
        "choosing columns:",
        "  --columns temp,rain,cond   exactly these, in this order",
        "  --columns=+wind,+hum       default columns plus wind and humidity",
        "  --columns=-rain,-feels     default columns minus these",
        "  --columns all              every column (same as -f / --full)",
        "  (use = when the list starts with + or -; aliases also work: humidity,",
        "   conditions, clouds, cover)",
        "",
        "defaults can be set with the environment variables WEATHER_COLUMNS,",
        "WEATHER_SKY=off and WEATHER_TIDES=off.",
    ]
    return "\n".join(lines) + "\n"


EXAMPLES_NWS = """
examples:
  nws                          next 24 hours at the default location
  nws --hours 48               next 48 hours
  nws -n 24x6                  next 6 days
  nws --zip 32202 -n 12        another ZIP code (downtown Jacksonville)
  nws --lat 30.33 --lon -81.66
  nws --full                   every column
  nws --zip 32202 --save-fav downtown    save a favorite, then: nws -F downtown
  nws --twilight astronomical  dawn/dusk at full dark instead of civil twilight
  nws --columns=+wind --no-tides
"""
EXAMPLES_OPEN_METEO = """
examples:
  open-meteo                   next 24 hours at the default location
  open-meteo --city Jacksonville -n 12
  open-meteo -n 24x7           a week (up to 16 days)
  open-meteo --city "Jacksonville, FL"
  open-meteo --zip 32202
  open-meteo --full            every column
  open-meteo --model dwd_icon_seamless  compare against another weather model
  open-meteo --city Jacksonville --save-fav home    then: open-meteo -F home
  open-meteo --city Jacksonville --columns temp,rain,cond
"""


def main():
    for stream in (sys.stdout, sys.stderr):   # emoji and box characters need UTF-8
        if (getattr(stream, "encoding", "") or "").lower().replace("-", "") != "utf8":
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError):
                pass
    name = Path(sys.argv[0]).stem.lower()    # "nws", "nws.exe" and "nws.cmd" all give "nws"
    args = sys.argv[1:]
    if name not in COMMANDS and args and args[0] in COMMANDS:
        name, args = args[0], args[1:]   # weather.py nws --hours 12
    if name not in COMMANDS:
        sys.exit("usage: weather.py {nws|open-meteo} [options]   (add -h for help)")

    # "-c -rain" would look like another option to argparse; join it as -c=-rain
    fixed, skip = [], False
    for i, a in enumerate(args):
        if skip:
            skip = False
        elif a in ("-c", "--columns") and i + 1 < len(args):
            fixed.append("--columns=" + args[i + 1])
            skip = True
        else:
            fixed.append(a)
    parser = build_parser(name)
    ns = parser.parse_args(fixed)

    def switch(value, env):
        if value is not None:
            return value
        return os.environ.get(env, "on").lower() not in ("0", "off", "no", "false")

    sky, tides = switch(ns.sky, "WEATHER_SKY"), switch(ns.tides, "WEATHER_TIDES")
    twilight = ns.twilight or os.environ.get("WEATHER_TWILIGHT", "civil").strip().lower()
    if twilight not in ("civil", "nautical", "astronomical", "none"):
        parser.error("twilight must be civil, nautical, astronomical or none: %s" % twilight)
    if ns.full and ns.columns is not None:
        parser.error("use either --full or --columns, not both")
    columns = parse_columns("all" if ns.full else ns.columns if ns.columns is not None else
                            os.environ.get("WEATHER_COLUMNS") or DEFAULT_COLUMNS)
    if ns.list_favs:
        list_favorites()
        return
    if ns.remove_fav:
        favs = load_favorites()
        key, _ = favorite_key(ns.remove_fav)
        if key not in favs:
            get_favorite(ns.remove_fav)          # exits with a helpful message
        gone = favs.pop(key)
        save_favorites(favs)
        print(f"Removed favorite '{gone['name']}'.")
        if key == saved_default_key():
            settings = load_settings()
            settings.pop("default_favorite", None)
            write_json(config_dir() / SETTINGS_FILE, settings, "settings")
            print(f"It was the default location, so the default is back to ZIP {DEFAULT_ZIP}.")
        return
    if ns.set_default:
        f = get_favorite(ns.set_default)         # exits with a helpful message if unknown
        settings = load_settings()
        settings["default_favorite"] = f["name"].lower()
        write_json(config_dir() / SETTINGS_FILE, settings, "settings")
        print(f"★ Default location is now '{f['name']}': {f['label']} · {f['lat']:.2f}, {f['lon']:.2f}")
        return
    if ns.clear_default:
        settings = load_settings()
        had = settings.pop("default_favorite", None)
        write_json(config_dir() / SETTINGS_FILE, settings, "settings")
        print(f"Default location is back to ZIP {DEFAULT_ZIP}." if had else
              f"No default favorite was set; the default is ZIP {DEFAULT_ZIP}.")
        return

    explicit = bool(ns.zip or getattr(ns, "city", None) or getattr(ns, "lat", None) is not None
                    or getattr(ns, "lon", None) is not None)
    if ns.fav and explicit:
        parser.error("use either --fav or a location (--zip/--city/--lat/--lon), not both")
    if ns.save_fav and (ns.fav or not explicit):
        parser.error("--save-fav needs a location to save: give --zip, --city or --lat/--lon")
    if not ns.fav and not explicit and not ns.save_fav:
        saved = default_favorite()               # the favorite chosen with --set-default
        if saved:
            ns.fav = saved["name"]
    try:
        fav_name = None
        if ns.fav:
            f = get_favorite(ns.fav)
            lat, lon, label, fav_name = f["lat"], f["lon"], f["label"], f["name"]
        elif name == "nws":
            lat, lon = ns.lat, ns.lon
            if (lat is None) != (lon is None):
                parser.error("--lat and --lon must be given together")
            if lat is not None and ns.zip:
                parser.error("use either --zip or --lat/--lon, not both")
            if lat is None:
                if ns.zip and not is_zip(ns.zip):
                    parser.error("ZIP must be 5 digits: %s" % ns.zip)
                zip_code = ns.zip or DEFAULT_ZIP
                lat, lon, place = zip_lookup(zip_code)
                label = f"ZIP {zip_code} center ({place})"
            else:
                label = "coordinates"
        else:
            if ns.city and ns.zip:
                parser.error("use either --city or --zip, not both")
            if ns.zip and not is_zip(ns.zip):
                parser.error("ZIP must be 5 digits: %s" % ns.zip)
            where = ns.city or ns.zip or DEFAULT_ZIP
            if ns.zip or not ns.city:
                lat, lon, place = zip_lookup(where)
                label = f"ZIP {where} center ({place})"
            else:
                lat, lon, place = geocode_city(where)
                label = f"{place} (city center)"
        if ns.save_fav:
            key, shown = favorite_key(ns.save_fav)
            favs = load_favorites()
            replaced = key in favs
            favs[key] = {"name": shown, "lat": round(lat, 4), "lon": round(lon, 4), "label": label}
            save_favorites(favs)
            print(f"★ {'Updated' if replaced else 'Saved'} favorite '{shown}': {label} · "
                  f"{lat:.2f}, {lon:.2f}\n")
        if name == "nws":
            nws(ns.hours or 24, lat, lon, columns, sky, tides, fav_name, twilight)
        else:
            model = (ns.model or os.environ.get("WEATHER_MODEL") or "").strip().lower()
            if model in ("", "best_match"):
                model = None
            elif not re.fullmatch(r"[a-z0-9_]+", model):
                parser.error("model names use letters, digits and underscores: %s" % model)
            open_meteo(ns.hours or 24, lat, lon, label, columns, sky, tides, fav_name, model, twilight)
    except ValueError:
        parser.error("could not understand the arguments (try -h)")
    except BrokenPipeError:
        pass


if __name__ == "__main__":
    main()
