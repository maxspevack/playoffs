# playoffs

One-screen terminal dashboard for the NHL and NBA playoffs. Stdlib only, single Python file, fits in 80 columns.

## Sample output

```
PLAYOFFS  Fri May 1 2026   updated 10:52 PM PDT

RECENT
  3h ago     NHL  R1 G6   VGK 5 @ UTA 1       VGK advances 4-2
  4h ago     NBA  R1 G6   LAL 98 @ HOU 78     LAL advances 4-2
  6h ago     NHL  R1 G6   BUF 4 @ BOS 1       BUF advances 4-2
  6h ago     NBA  R1 G6   CLE 110 @ TOR 112   tied 3-3
  6h ago     NHL  R1 G6   TB 1 @ MTL 0        tied 3-3
  6h ago     NBA  R1 G6   DET 93 @ ORL 79     tied 3-3

TOMORROW
  4:30 PM   NBA  R1 G7 ★   PHI @ BOS
  5:00 PM   NHL  R2 G1     PHI @ CAR

NHL Round 2 (2 active)
  CAR vs PHI                 G1 tomorrow
  COL vs MIN                 G1 May 3

NHL Round 1 (1 active · 7 done)
  MTL vs TB       tied 3-3   G7 May 3 ★     MTL·TB·MTL·TB·MTL·TB
  done: ANA-EDM 4-2 · BUF-BOS 4-2 · CAR-OTT 4-0 · COL-LA 4-0 · MIN-DAL 4-2
        PHI-PIT 4-2 · VGK-UTA 4-2

NBA Round 2 (2 active)
  MIN vs SA                  G1 May 3
  LAL vs OKC                 G1 May 4

NBA Round 1 (3 active · 5 done)
  CLE vs TOR      tied 3-3   G7 May 3 ★     CLE·CLE·TOR·TOR·CLE·TOR
  BOS vs PHI      tied 3-3   G7 tomorrow ★  BOS·PHI·BOS·BOS·PHI·PHI
  DET vs ORL      tied 3-3   G7 May 3 ★     ORL·DET·ORL·ORL·DET·DET
  done: LAL-HOU 4-2 · MIN-DEN 4-2 · NY-ATL 4-2 · OKC-PHX 4-0 · SA-POR 4-1
```

When live games are happening, a `LIVE NOW` section appears at the top instead of `RECENT`, sorted by score gap (closest first) with closeout/stay-alive markers:

```
LIVE NOW
  NHL  TB 0 @ MTL 0       8:33 - 3rd    G6 ★ closeout       MTL leads 3-2
  NHL  BUF 2 @ BOS 1      End of 2nd    G6 ★ closeout       BUF leads 3-2
  NBA  ORL 88 @ DET 87    4:24 - 4th    G6 ★ closeout       ORL leads 3-2
  NBA  CLE 74 @ TOR 85    3:40 - 3rd    G6 ★ stay alive     CLE leads 3-2
```

## Run

Run it directly — stdlib only, no install step required:

```sh
python3 playoffs.py
```

Tested on Python 3.9+.

To put it on your `$PATH`, symlink it:

```sh
mkdir -p ~/.local/bin
ln -s "$(pwd)/playoffs.py" ~/.local/bin/playoffs
```

For ambient awareness during a game night:

```sh
watch -n 60 playoffs
```

## Sections

| Section | When shown | Contents |
|---|---|---|
| `LIVE NOW` | Whenever games are in progress | Live games sorted by score gap, with closeout (yellow ★) for series-leader winning, stay-alive (green ★) for trailer winning, G7 marker for 3-3 series |
| `RECENT` | Only when `LIVE NOW` is empty | Completed games from the most recent slate, found by walking back through final games until a >6h gap. Rows older than 8h are dimmed. |
| `LATER TODAY` | Today's scheduled games not yet started | Time, league, round/game tag, matchup |
| `TOMORROW` | Tomorrow's scheduled games | Same format as `LATER TODAY`, with "if X wins" tag on G7s contingent on tonight's outcome |
| Per-league round sections | Always | Active series with score, next-game info, game-by-game winner sequence; completed series rolled into a single `done:` line per round |

## Configuration

| Environment variable | Effect |
|---|---|
| `NO_COLOR` | Disable ANSI colors (per [no-color.org](https://no-color.org)). Presence of the variable matters, regardless of value. |
| `FORCE_COLOR` | Force colors even when stdout isn't a TTY. Useful for piping through `less -R`. |

## How it works

Pipeline: `gather → normalize → group → render`.

1. **gather**: Two parallel HTTPS requests to ESPN's public scoreboard endpoint, one per league, each using a date-range query covering the entire playoff window. Replaces what would otherwise be ~50 single-day requests.
2. **normalize**: Translate ESPN's `"Lakers/Rockets"` placeholder strings (used for unresolved Round 2+ slots) to `"LAL/HOU"` style. Once a Round 1 series is decided, resolve the placeholder to the actual winner so duplicate Round 2 entries collapse into one series.
3. **group**: Bucket games by `(league, frozenset({home, away}))` to recover series. Sort each series by date.
4. **render**: Print sections with column-aligned formatting. Auto-hide rules (LIVE NOW takes priority over RECENT) make the dashboard adaptive without per-section configuration.

Total runtime: ~500ms.

## Design notes

- **Derived state over reported state.** ESPN's `series.completed` flag can lag by hours after the deciding game ends. The dashboard computes done-state from the win count (`max(wins) >= 4`) instead. When the API and the data disagree, the data wins.
- **Range queries instead of caching.** Two range queries replace single-day fetching. Disk caching was prototyped and removed once the underlying volume dropped 24x; the access pattern itself was the optimization.
- **Score-gap sort in LIVE NOW.** `abs(home_score - away_score)` is a direct proxy for "should I tune in?" – a 1-point game with 4 minutes left ranks above a 20-point blowout, regardless of game number or start time.
- **Boundary validation.** `_is_valid` runs twice in `gather()` – once before normalize (drops `TBD vs TBD` placeholders) and once after (defends against any same-team edge case introduced by placeholder resolution). Validate at the seam, trust the room.

## Development

From the repo root:

```sh
python3 -m pytest tests/
```

Tests cover the logic helpers (`_safe_int`, `count_wins`, `is_series_done`, `round_num`, `fmt_state`, `elim_status_live`, `normalize_placeholders`, `find_recent_games`, `contingent_tag`, `parse`, `fmt_when`). No network access; all tests use synthetic game dicts.

The suite has caught one real bug that production data was masking: `round_num` returning 3 for "Conference Semifinals" because "semifinals" contains "final". ESPN happens to use "1st Round" / "2nd Round" naming so the bug was dormant; the test forced the issue.

## Files

```
playoffs/
├── playoffs.py             # main script, stdlib only
├── tests/
│   ├── conftest.py
│   └── test_playoffs.py
├── README.md
├── LICENSE
└── .gitignore
```

## Limitations

- `PLAYOFF_START = date(2026, 4, 15)` is hardcoded. Update for future seasons or compute from the calendar.
- Times use the system's local timezone via `datetime.astimezone()` and `%Z` strftime. If your terminal lies about its locale, times will too.
- No offline mode – an ESPN outage produces "No playoff games found."
- WNBA / college basketball / NFL playoffs not supported. Adding them is one entry in the `LEAGUES` constant plus verification that ESPN uses the same JSON shape.

## ESPN endpoint reference

```
https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard?dates={range}&seasontype=3
```

- `sport / league`: `hockey / nhl`, `basketball / nba`
- `dates`: `YYYYMMDD` for one day, `YYYYMMDD-YYYYMMDD` for a range
- `seasontype=3`: post-season (excludes regular season and exhibitions)

Per-event round and game number live at `competitions[0].notes[0].headline` (e.g., `"East 1st Round - Game 6"`). Series state lives at `competitions[0].series.summary` but the score-derived computation is more reliable.

## License

MIT. See `LICENSE`.
