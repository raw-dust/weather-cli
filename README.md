# weather-cli

Hourly weather forecasts in your terminal. It prints a compact, colored table
with one row per hour (temperature, feels-like, rain chance, sky cover, wind,
humidity and conditions), plus sunrise, sunset, twilight, moon and tide
information for the day. You can save favorite places and choose exactly which
columns to show.

It is one stdlib-only Python script (`weather.py`). It runs on Linux, macOS and
Windows, in any shell (bash, zsh, fish, PowerShell, cmd), and needs Python 3.7
or newer and nothing else: no pip packages, no `jq`, no API keys.

## Where the data comes from

- **[National Weather Service (NWS)](https://www.weather.gov)** is the US
  government's official weather agency, part of NOAA. Its forecasts are
  prepared by local forecast offices on a fine grid and published through a
  free, key-less [web API](https://www.weather.gov/documentation/services-web-api).
  It covers the US and its territories only.
- **[Open-Meteo](https://open-meteo.com)** is an open-source weather API that
  gathers forecasts from national weather services around the world (NOAA,
  Germany's DWD, ECMWF, Environment Canada and others) and serves them through
  one simple interface. It is free for non-commercial use without a key; see
  its [documentation](https://open-meteo.com/en/docs) and
  [terms](https://open-meteo.com/en/terms). It covers anywhere in the world.

Sunrise, sunset, twilight and the moon are calculated by the script itself,
tides come from [NOAA](https://tidesandcurrents.noaa.gov) tide predictions, and
ZIP codes are looked up with [zippopotam.us](https://zippopotam.us) (all
details below).

## The two commands

| Command | Forecast from | Coverage |
|---|---|---|
| `nws` | National Weather Service API (`api.weather.gov`) | US only, about 6.5 days (156 hours) of hourly data |
| `open-meteo` | Open-Meteo | Worldwide, 3 days of hourly data |

Both take the same options and print the same table, so you can run them side
by side and compare. Install them below, then see [Usage](#usage).

## Install

Pick one. All of them give you the commands `nws` and `open-meteo`.

**1. pip / pipx (any system, recommended).** From this folder:

```bash
pipx install .          # or: pip install --user .
```

pip creates the `nws` and `open-meteo` commands for you (`.exe` launchers on
Windows) and puts them on your PATH. `pipx` keeps the install isolated and is
the cleanest; `pip install --user .` works too. Update the same way after
editing the script (`pipx install --force .`).

**2. Symlinks (Linux and macOS, no pip).** The script picks its behavior
from the name it was called as, so each command is a symlink to it. They go
in `~/.local/bin`, which must be on your PATH.

```bash
chmod +x weather.py
ln -s "$PWD/weather.py" ~/.local/bin/nws
ln -s "$PWD/weather.py" ~/.local/bin/open-meteo
```

Because the symlinks point at the file, editing the script takes effect
immediately. Re-run `ln -sf` if you move the folder.

**3. Run the script directly (any system, nothing to install).**

```bash
python3 weather.py nws --zip 32202 -n 12    # Windows: py weather.py nws ...
python3 weather.py open-meteo --city Jacksonville
```

### Platform notes

| | Linux | macOS | Windows |
|---|---|---|---|
| Tide cache | `~/.cache/weather-cli` (or `$XDG_CACHE_HOME`) | `~/Library/Caches/weather-cli` | `%LOCALAPPDATA%\weather-cli` |
| Colors | any terminal | Terminal, iTerm | Windows Terminal, PowerShell, cmd on Windows 10+ (enabled automatically) |
| Emoji | needs an emoji font (Noto Color Emoji) | built in | Windows Terminal is best; the old console host may show boxes |

- **Windows:** use `py` or `python` instead of `python3`. If you installed
  with `pip install --user`, make sure Python's `Scripts` folder is on your
  PATH (the installer prints its location). Output is forced to UTF-8, so
  the `°`, box lines and emoji don't fail when piped or redirected.
- **macOS:** python.org installers of Python don't trust any certificates
  until you run **Install Certificates.command** (in
  `/Applications/Python 3.x/`). Without it every request fails with a
  certificate error. Homebrew Python is fine.
- **Setting the options permanently** (`WEATHER_COLUMNS`, `WEATHER_SKY`,
  `WEATHER_TIDES`, `WEATHER_UA`):
  - bash/zsh: `export WEATHER_SKY=off` in `~/.bashrc` or `~/.zshrc`
  - fish: `set -gx WEATHER_SKY off`
  - PowerShell: `[Environment]::SetEnvironmentVariable("WEATHER_SKY","off","User")`
  - cmd: `setx WEATHER_SKY off`

## Usage

When you don't give a location, both commands use the **default location**:
US ZIP code **32277** (Jacksonville, FL) out of the box, or your own favorite
if you set one (see [Changing the default location](#changing-the-default-location)).
A ZIP code is turned into coordinates with
[zippopotam.us](https://api.zippopotam.us) (US only, no key).

Every setting is a named option, so there is nothing to remember about
argument order. `nws -h` and `open-meteo -h` list them all.

| Option | Meaning |
|---|---|
| `-h`, `-?`, `--help` | show the help (every option, the column list, examples) |
| `-n`, `--hours N` | hours to show (default 24; `nws` goes up to 156) |
| `-z`, `--zip ZIP` | US ZIP code |
| `--lat DEG --lon DEG` | coordinates (`nws` only, used together) |
| `-C`, `--city NAME` | city name, anywhere in the world (`open-meteo` only) |
| `-F`, `--fav NAME` | use a saved favorite location (see below) |
| `--save-fav NAME` | save the location you gave as a favorite |
| `--list-favs`, `--remove-fav NAME` | list or delete favorites |
| `--set-default NAME`, `--clear-default` | choose which favorite is used when no location is given, or go back to the built-in ZIP |
| `--model NAME` | Open-Meteo weather model (`open-meteo` only; see below) |
| `-c`, `--columns LIST` | columns to show (see below) |
| `-f`, `--full` | show every column (same as `--columns all`) |
| `--sky` / `--no-sky` | sun and moon lines and sunrise/sunset markers |
| `--twilight KIND` | twilight on the sun line: `civil` (default), `nautical`, `astronomical` or `none` |
| `--tides` / `--no-tides` | tide line and markers |

### `nws`

```bash
nws                                   # next 24 hours at the default location
nws --hours 48                        # next 48 hours (or -n 48)
nws -n 156                            # the whole forecast (about 6.5 days)
nws --zip 32202 -n 12                 # another ZIP code (downtown Jacksonville)
nws --lat 30.33 --lon -81.66          # explicit coordinates
```

### `open-meteo`

```bash
open-meteo                            # default location, next 24 hours
open-meteo --zip 32202                # another US ZIP code
open-meteo --city Jacksonville        # a city by name
open-meteo -C "Jacksonville, FL" -n 6 # quote anything with spaces
```

`--city` takes any city in the world (`nws` is US only). Add a state or
country code after a comma to pick the right one (`"Jacksonville, FL"`); the
comma is optional for a two-letter code. `St`, `Ft`, `Mt`, `Jax` and `Bch` are expanded to
Saint, Fort, Mount, Jacksonville and Beach (the geocoder only knows the full words), and if nothing
matches you get a hint instead of a guess.

`--zip` and `--city` can't be combined, and `nws` won't take both `--zip` and
`--lat/--lon`; you get a clear error instead of a guess.

In bash and zsh an unquoted `-?` is a wildcard and can expand to a file named
`-a`, `-b`, etc. in the current folder; quote it (`'-?'`) or use `-h`. fish and
PowerShell don't expand it.

The title says exactly which point was used, for example
`Open-Meteo hourly forecast: ZIP 32277 center (Jacksonville, FL) · 30.37, -81.59`
or `... Jacksonville, Florida (city center) · 30.33, -81.66`. (`nws` instead
names the nearest city and the NWS forecast grid cell, for example
`NWS hourly forecast: Jacksonville, FL · NWS grid JAX 68,67`.)

You can also run the script directly, naming the command first:
`python3 weather.py nws --zip 32202` or `python3 weather.py open-meteo --city Jacksonville`.

### Choosing the Open-Meteo model

Open-Meteo blends many national weather models. By default (`best_match`) it
picks the best one for the location and doesn't say which; in my tests for
Jacksonville the numbers matched NOAA's GFS exactly. `--model NAME` (or the `WEATHER_MODEL`
environment variable) forces a specific model, and the title then ends with
`· model NAME`:

```bash
open-meteo --model icon_seamless
open-meteo --model ecmwf_ifs025 -n 12 -c time,temp,rain,cond
```

| Model | Source |
|---|---|
| `best_match` | automatic choice for the location (the default) |
| `gfs_seamless` | NOAA GFS, USA |
| `icon_seamless` | DWD ICON, Germany |
| `ecmwf_ifs025` | ECMWF IFS, Europe |
| `gem_seamless` | Environment Canada GEM |
| `meteofrance_seamless` | Météo-France |
| `ukmo_seamless` | UK Met Office |
| `jma_seamless` | Japan Meteorological Agency |

These eight are the ones I tested; Open-Meteo has 30 or more (see
[open-meteo.com/en/docs](https://open-meteo.com/en/docs)) and any valid name
works. Models can disagree noticeably: on one test day they differed by up to
8°F at the same hour for Jacksonville. A model may leave a column empty (Météo-France
and JMA publish no rain chance, so it shows `-`) or stop before the end of the
three days. An unknown name gives a message listing the choices above. `nws` is
not an Open-Meteo model, so it has no `--model` option; running it next to
`open-meteo --model ...` is a good way to compare forecasts.

### Favorite locations

Save places you check often and recall them by name with `-F` (or `--fav`).
Favorites work with both commands.

```bash
nws --zip 32202 --save-fav downtown           # save it (and show the forecast)
open-meteo --city "Jax Bch FL" --save-fav beach
nws -F beach                                  # use it
open-meteo -F beach -n 12 --no-tides
nws --list-favs                               # see what's saved
nws --remove-fav downtown                     # delete one
```
```
★ Saved favorite 'downtown': ZIP 32202 center (Jacksonville, FL) · 30.33, -81.65

Favorite locations
  ★ beach     Jacksonville Beach, Florida (city center)  ·  30.29, -81.39
  ★ downtown  ZIP 32202 center (Jacksonville, FL)        ·  30.33, -81.65
```

- **Saving** needs a location to save: `--zip`, `--city` (`open-meteo` only) or
  `--lat` with `--lon` (`nws` only). Saving again under the same name updates
  it. Names are 1 to 30 characters, case-insensitive, and may contain spaces
  (quote them): `--save-fav "my house"`.
- **Using** one replaces `--zip`, `--city` and `--lat/--lon`; combining them is
  an error. The title gets a `★ name` tag, for example
  `NWS hourly forecast: Jacksonville Beach, FL · NWS grid JAX 76,64 · ★ beach`.
- **Default:** `--set-default NAME` makes a favorite the location used when you
  give none (see [below](#changing-the-default-location)).
- **A typo** gets a suggestion: `No favorite named 'beech'. Did you mean 'beach'?`
- **Stored as coordinates**, so using a favorite doesn't need a ZIP or city
  lookup. A favorite saved from a city or ZIP works in either command, but with
  `nws` it must be inside the US.
- **Where:** a small JSON file you can read or edit,
  `~/.config/weather-cli/favorites.json` on Linux (or under
  `$XDG_CONFIG_HOME`), `~/Library/Application Support/weather-cli/` on macOS,
  `%APPDATA%\weather-cli\` on Windows. It stays on your machine; nothing about
  your favorites is sent anywhere except the coordinates in a normal forecast
  request.

## Example output

```
NWS hourly forecast: Jacksonville, FL · NWS grid JAX 68,67
🌄 Dawn 6:33 AM  ·  🌅 Sunrise 6:58 AM  ·  🌇 Sunset 5:26 PM  ·  🌆 Dusk 5:52 PM
⬆ Moonrise 4:27 PM  ·  ⬇ Moonset 5:55 AM  ·  🌔 Waxing gibbous (98%)
🌊 Low 1:07 AM 0.0 ft  ·  High 7:24 AM 4.5 ft  ·  Low 2:08 PM 0.2 ft  ·  High 7:47 PM 3.9 ft
    (Dame Point, FL, 2 mi)

Date         Time  Temp °F  Rain %  Conditions
──────────  ─────  ───────  ──────  ──────────
11/23/2026   3 AM       61       0  ☁️ Mostly cloudy
             4 AM       61       1  ☁️ Cloudy
             5 AM       61       0  ☁️ Mostly cloudy
             6 AM       60       0  ☁️ Mostly cloudy   🌅 6:58 AM
```

One row per hour, starting at the current hour, in the forecast location's
local time. The date (`mm/dd/yyyy`) only appears when the day changes.
Units are in the header: temperature °F, feels-like °F, rain chance %,
and (when enabled) humidity %, cloud cover % and wind mph with compass
direction, speed and gust in parentheses. `open-meteo` prints the same
table. In both commands gusts are shown only when they exceed the sustained
wind by 5 mph or more.

More examples:

```bash
nws --full -n 3 --no-sky --no-tides
```
```
NWS hourly forecast: Jacksonville, FL · NWS grid JAX 68,67

Date         Time  Temp °F  Rain %  Cloud %  Wind mph  Hum %  Conditions
──────────  ─────  ───────  ──────  ───────  ────────  ─────  ──────────
11/22/2026   3 PM       68       4       79    W 12       93  ☁️ Mostly cloudy
             4 PM       68       6       79    W 12       93  ☁️ Mostly cloudy
             5 PM       68       9       78    W  9       90  ☁️ Mostly cloudy
```

```bash
open-meteo --city "Jacksonville, FL" -n 3 -c time,temp,rain,cond --no-tides
```
```
Open-Meteo hourly forecast: Jacksonville, Florida (city center) · 30.33, -81.66
🌅 Sunrise 6:58 AM  ·  🌇 Sunset 5:27 PM
⬆ Moonrise 3:45 PM  ·  ⬇ Moonset 4:48 AM  ·  🌔 Waxing gibbous (95%)

 Time  Temp °F  Rain %  Conditions
─────  ───────  ──────  ──────────
 3 PM       65       0  ☁️ Overcast
 4 PM       64       0  ☁️ Overcast
 5 PM       64       2  ☁️ Overcast   🌇 5:27 PM
```

### Sun and moon lines

Under the title, two gray lines show dawn, sunrise, sunset and dusk for the first
day in the table, then moonrise, moonset and the moon phase (with how much of it
is lit):

```
🌄 Dawn 6:33 AM  ·  🌅 Sunrise 6:58 AM  ·  🌇 Sunset 5:26 PM  ·  🌆 Dusk 5:52 PM
⬆ Moonrise 4:27 PM  ·  ⬇ Moonset 5:55 AM  ·  🌔 Waxing gibbous (98%)
```

- **Twilight:** dawn and dusk are **civil twilight** by default, when the sun
  is 6° below the horizon (enough light to see outdoors without lamps).
  `--twilight nautical` (12°) or `--twilight astronomical` (18°, full dark)
  switch the two times, relabeled "Nautical dawn/dusk" and "Astro dawn/dusk";
  `--twilight none` removes them. `WEATHER_TWILIGHT=none` changes the default.
  Neither Open-Meteo nor the NWS API provides twilight, so it is calculated with
  the same sunrise equation as above, at a different sun angle. It matched
  sunrise-sunset.org to within 2 minutes (mean 0.3) for all three kinds in 6
  cities on 4 dates, including both solstices, and matched the Naval
  Observatory's civil twilight exactly in Jacksonville and Denver. Where the sun
  never gets that low (high latitudes in summer) dawn and dusk are left out.
- **Sunrise/sunset:** `open-meteo` takes them from Open-Meteo. `nws` has no
  sun data in its API, so the script **calculates** them from the location
  with the standard NOAA sunrise equation (no extra request). It matched
  Open-Meteo to within about 2 minutes at seven test locations.
- **Moon:** the phase, moonrise and moonset are calculated for both commands
  (neither source provides them). Checked against the US Naval Observatory
  at 6 cities on 3 dates: the average error was about 6 minutes, and the
  worst was 25 minutes (Anchorage). The lit percentage is within a couple of
  points. For exact times, consult the Naval Observatory.
- **"none":** the moon rises about 50 minutes later each day, so about once a
  month there is a calendar day with no moonrise (and another with no
  moonset). That day shows `none`.
- **Times** are in the forecast location's local time. Moonset often falls
  after midnight, so it can be earlier on the clock than moonrise.
- In polar regions the sun line says "Sun up all day" or "Sun down all day".
- **Table markers:** the hour that contains sunrise or sunset is flagged at
  the end of its row with the exact time, so you can see when the light
  changes (they follow the `cond` column, so they disappear if you hide it):

  ```
               5 PM       68       9  ☁️ Mostly cloudy   🌇 5:27 PM
               ...
               6 AM       61       1  ☁️ Mostly cloudy   🌅 6:58 AM
  ```

- The day/night icons come from the forecast services' own day/night flags, not
  from these sunrise and sunset times: clear hours after dark show 🌙 and
  partly cloudy ones show ☁️ instead of ⛅. The flags match the sun times except
  in the hours that contain sunrise or sunset, which the NWS counts as day (I
  checked 72 hours). The icons don't depend on `--no-sky`.

To hide both lines (twilight included) and the sunrise/sunset row markers, add `--no-sky`; `--sky`
shows them again. It can go anywhere on the command line and combines with
`--columns`:

```bash
nws --no-sky
open-meteo --city Jacksonville -n 12 --no-sky -c time,temp,cond
```

To hide them by default, set `WEATHER_SKY=off` (for example in fish:
`set -gx WEATHER_SKY off`). `--sky` still overrides it for a single run.
Hiding the lines skips the moon calculation, but `nws` still computes
sunrise and sunset because the day/night icons need them.

### Tides

Near the coast (or a tidal river) a third line under the title lists the first
day's high and low tides, and every high and low in the whole table is flagged
on the hour it happens (the markers show `H` or `L` and the time only; the full
words and heights are on the summary line):

```
🌊 Low 12:16 AM 0.2 ft  ·  High 6:32 AM 4.4 ft  ·  Low 1:13 PM 0.4 ft  ·  High 6:53 PM 3.9 ft
    (Dame Point, FL, 2 mi)
```

```
             6 PM  ☁️ Mostly cloudy   🌊 H 6:53 PM
             1 AM  ☁️ Mostly cloudy   🌊 L 1:07 AM
             7 AM  ☁️ Mostly cloudy   🌊 H 7:24 AM
```

- **Source:** NOAA's CO-OPS tide predictions (free, no key), for the nearest
  prediction station within 25 miles. The station name and distance are shown
  (on the same line if it fits your terminal, otherwise below). These are
  NOAA's own harmonic predictions, not an estimate.
- **Heights** are in feet above MLLW (mean lower low water, the usual chart
  datum), so a low tide can be negative. Times are local to the station.
- **Summary line:** the first day in the table only, like the sun and moon
  lines, so it stays one line however long the forecast is. It also names the
  station.
- **Markers:** one per high or low across the whole forecast period (about 4
  a day, so `nws -n 156` shows 6 days of tides). They follow the `cond` column,
  before any sunrise/sunset marker, and are blue when color is on.
- **Coverage:** US coasts, tidal rivers, and US territories. Inland
  locations and places outside the US show no tide line. The
  station list (about 370 KB) is downloaded once and cached in
  `~/.cache/weather-cli/tide-stations.json` for 30 days. Only the station ID
  goes to NOAA when fetching predictions, not your location.
- **Hide it:** `--no-tides` hides both the line and the markers (or
  `WEATHER_TIDES=off` for a default; `--tides` overrides it). `--no-sky` hides
  only the sun and moon lines, and the two switches are independent. If NOAA can't be reached, the line is quietly
  left out.

### Choosing columns

Every column can be shown or hidden with `-c` / `--columns LIST`.

| Column | Shows |
|---|---|
| `date` | `mm/dd/yyyy`, only when the day changes |
| `time` | 12-hour time |
| `temp` | temperature °F |
| `feels` | feels-like °F (see below) |
| `rain` | chance of rain % |
| `cloud` | sky cover %, 0 clear to 100 overcast (aliases `clouds`, `cover`); hidden by default |
| `wind` | direction, speed mph, gust |
| `hum` | humidity % (alias `humidity`); hidden by default |
| `cond` | emoji + conditions text (aliases `conditions`, `weather`); always drawn last |

**Cloud cover, wind and humidity are hidden by default.** The default columns
are `date,time,temp,feels,rain,cond`.

```bash
nws --columns=+wind,+hum              # default columns plus wind and humidity
nws --columns=-rain,-feels            # default columns minus these
nws -n 12 -c time,temp,rain           # exactly these, in this order
open-meteo --city Jacksonville -c temp,cond
nws --columns=+cloud                  # add sky cover
nws --full                            # everything (or --columns all, or -f)
```

Write a list that starts with `+` or `-` as `--columns=-rain` (with the `=`).
Use commas and no spaces.

A list made only of `+name` / `-name` entries adjusts the default; any other
list is used as given. To change the default permanently, set
`WEATHER_COLUMNS` (for example in `~/.bashrc` or fish's `config.fish`:
`set -gx WEATHER_COLUMNS date,time,temp,rain,wind,cond`), or edit
`DEFAULT_COLUMNS` in `weather.py`. `nws -h` prints the same help.

### Feels like

The `feels` column appears only when at least one hour differs from the
actual temperature by 3°F or more (`FEELS_MIN_DIFF` in `weather.py`), and
rows within 3°F are left blank so the column doesn't add noise.

- `nws`: the NWS **apparent temperature**, which is the heat index in hot
  weather and the wind chill in cold weather (the official NWS values, and
  available all year).
- `open-meteo`: Open-Meteo's `apparent_temperature`, which accounts for
  humidity and wind. It is similar to, but not identical to, the NWS heat
  index and wind chill.

### Colors

Values are colored by range. Temperature runs from blue (cold) to red (hot),
and wind from green (calm) to red (strong). Rain, humidity and cloud cover use
their own scales:

| Column | Colors |
|---|---|
| Temp °F | ≤32 blue, 33-49 cyan, 50-64 yellow, 65-79 green, 80-89 orange, 90+ red |
| Feels °F | same scale as Temp |
| Rain % | <20 gray, 20-49 light blue, 50-79 blue, 80+ deep blue |
| Wind mph | <10 green, 10-19 yellow, 20-29 orange, 30+ red |
| Cloud % | <20 sky blue, 20-39 light blue, 40-59 pale blue, 60-79 light gray, 80+ gray |
| Hum % | <30 yellow, 30-59 green, 60-79 cyan, 80+ blue |

Color is automatic: it's off when output is piped or redirected
(`nws | less`, `nws > file`) and when the `NO_COLOR` environment variable is
set. `FORCE_COLOR=1` turns it on regardless (e.g. `FORCE_COLOR=1 nws | less -R`).
The thresholds are small lists at the top of `weather.py` (`TEMP_COLOR`,
`RAIN_COLOR`, `WIND_COLOR`, `CLOUD_COLOR`, `HUM_COLOR`) if you want to tune them.

The icons are emoji (☀️ 🌤️ ⛅ ☁️ 🌦️ 🌧️ ⛈️ 🌨️ 🌫️ 🌙), so your terminal needs an
emoji font (Noto Color Emoji works in Konsole). Night hours show 🌙 for clear
skies. Day versus night comes from the forecast services themselves (the NWS
day/night flag for `nws`, Open-Meteo's for `open-meteo`).

## Configuration

### Changing the default location

The default location is what `nws` and `open-meteo` use when you give no
`--zip`, `--city`, `--lat/--lon` or `--fav`. Out of the box it is ZIP **32277**.
To change it, save the place as a favorite and make that favorite the default:

```bash
nws --zip 32202 --save-fav downtown     # 1. save the place (skip if it is already a favorite)
nws --set-default downtown              # 2. make it the default
nws                                     # now uses downtown, for nws and open-meteo
nws --list-favs                         # shows which favorite is the default
nws --clear-default                     # go back to the built-in ZIP 32277
```

- **No editing needed.** The choice is saved in `settings.json` next to
  `favorites.json` (`~/.config/weather-cli/` on Linux, `~/Library/Application
  Support/weather-cli/` on macOS, `%APPDATA%\weather-cli\` on Windows), so it
  applies to both commands, in every shell.
- **Order of precedence:** an explicit `--zip`, `--city` or `--lat/--lon`, then
  `-F NAME`, then the default favorite, then the built-in ZIP. So a one-off
  `nws --zip 80202` or `nws -F beach` always overrides the default.
- **Titles** for the default favorite carry the usual `★ name` tag, so you can
  tell it is in use. `nws -h` shows the current default in its "location"
  heading and in the favorites section.
- **If the default favorite is deleted** (`--remove-fav`), the default goes back
  to the built-in ZIP automatically. If `settings.json` points at a favorite
  that no longer exists (for example after hand-editing), you get a warning and
  the built-in ZIP is used.
- **Changing the built-in fallback** itself is one line near the top of
  `weather.py`, if you want a different ZIP for everyone who runs this copy:

  ```python
  DEFAULT_ZIP = "32277"   # US ZIP code used when no location and no default favorite is set
  ```

### Units

Units (°F, mph) are fixed. For Open-Meteo, change `temperature_unit` and
`wind_speed_unit` in the `open_meteo()` function. `nws` asks the API for US units
(°F, mph).

## Notes

- **NWS data:** `nws` makes three requests: the point lookup, the hourly
  forecast (temperature, rain chance, humidity, wind, the NWS's own
  short-forecast text such as "Chance rain showers", and a day/night flag) and
  the raw forecast grid (sky cover, wind gusts, apparent temperature). If the
  grid request fails, the table still prints without the cloud, gust and
  feels-like values. Server errors are retried twice. The API is free and
  needs no key, but rejects requests that have no User-Agent (the script
  always sends one). The forecast covers about 6.5 days, so `--hours` above 156
  just shows everything available.
- **Outside the US:** `nws` says the NWS has no forecast for that location.
  Use `open-meteo` there.
- **User-Agent and contact info:** every request sends the generic
  `weather-cli`. The NWS and NOAA ask clients to identify themselves with a
  contact address, so you can opt in by setting `WEATHER_UA`:

  ```bash
  export WEATHER_UA="weather-cli (Jane Doe, jane@example.com)"    # bash/zsh (Linux, macOS)
  set -gx WEATHER_UA "weather-cli (Jane Doe, jane@example.com)"   # fish
  ```

  ```powershell
  [Environment]::SetEnvironmentVariable("WEATHER_UA", "weather-cli (Jane Doe, jane@example.com)", "User")   # PowerShell, permanent
  ```

  ```bat
  setx WEATHER_UA "weather-cli (Jane Doe, jane@example.com)"      :: cmd, permanent
  ```

  Put the bash/zsh line in `~/.bashrc` (Linux) or `~/.zshrc` (macOS) and the
  fish line in `~/.config/fish/config.fish` to keep it. On Windows the two
  commands above are already permanent; open a new terminal afterward. To try
  it for one session only, use `$env:WEATHER_UA = "..."` in PowerShell.

  When set, it is sent **only** to `api.weather.gov` and NOAA's
  `tidesandcurrents.noaa.gov` (the US agencies that ask for it). Open-Meteo and
  zippopotam.us always get the generic name, so your contact details never go to
  third parties. Leave it unset to stay anonymous.
- **Bad ZIP codes** print `ZIP code not found: ...`. **Network errors**
  print `Request failed: ...`. Both exit with status 1.
- Running `weather.py` without `nws` or `open-meteo` after it prints a one-line
  usage message.

## Uninstall

```bash
pipx uninstall weather-cli            # or: pip uninstall weather-cli
rm ~/.local/bin/nws ~/.local/bin/open-meteo   # only if you used symlinks
rm -r ~/.cache/weather-cli            # tide station cache (path per platform above)
rm -r ~/.config/weather-cli           # saved favorites (path per platform above)
```
