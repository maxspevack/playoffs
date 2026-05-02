#!/usr/bin/env python3
"""One-stop terminal view of NHL + NBA playoffs. Stdlib only."""

import json
import os
import re
import sys
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

ESPN = "https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard"
LEAGUES = [("NHL", "hockey", "nhl"), ("NBA", "basketball", "nba")]
PLAYOFF_START = date(2026, 4, 15)
LOOKAHEAD_DAYS = 90
RECENT_GAP_HOURS = 6
DIM_AGE_HOURS = 8
HTTP_TIMEOUT = 10
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
ROUND_LABEL = {1: "Round 1", 2: "Round 2", 3: "Conference Finals", 4: "Finals"}
LEAGUE_ORDER = {"NHL": 0, "NBA": 1}

# Visible-cell column widths for terminal layout. ANSI codes excluded.
COL_SCORE = 18      # "ABC 99 @ DEF 99"
COL_STATUS = 12     # "12:34 - 3rd"
COL_AGO = 9         # "Xh ago"
COL_TAG = 8         # "R1 G7 ★" (TOMORROW / LATER TODAY)
COL_TAG_RECENT = 6  # "R1 G7" (RECENT, no star)
COL_TIME = 8        # "9:00 PM"
COL_TEAMS = 14      # "ABC vs DEF" or "ABC/DEF vs GHI"
COL_STATE = 9       # "TEAM 3-2" or "tied 3-3"
COL_WHEN = 13       # "G7 tomorrow ★"
DONE_LINE_MAX = 70

COLOR = (sys.stdout.isatty() or os.environ.get("FORCE_COLOR")) and "NO_COLOR" not in os.environ
ANSI = {"bold": 1, "dim": 2, "red": 31, "green": 32, "yellow": 33, "cyan": 36}


def st(text, *styles):
    if not COLOR or not styles: return text
    return "".join(f"\033[{ANSI[s]}m" for s in styles) + text + "\033[0m"


def _safe_int(v):
    try: return int(v)
    except (TypeError, ValueError): return 0


def fetch(url):
    """Fetch JSON from a URL. Returns the events list, or None on network/parse error."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            return json.load(r).get("events", [])
    except (OSError, json.JSONDecodeError) as e:
        # OSError covers urllib.error.URLError, HTTPError, TimeoutError, ConnectionError
        print(f"warn: {url}: {type(e).__name__}: {e}", file=sys.stderr)
        return None


def round_num(headline):
    h = headline.lower()
    if "stanley cup" in h or "nba finals" in h: return 4
    if "2nd" in h or "semi" in h: return 2  # check before "conf+final" since "semifinals" contains "final"
    if "conf" in h and "final" in h: return 3
    if "1st" in h or "first" in h: return 1
    return 0


def parse(event, league):
    """Returns a normalized game dict, or None if the event lacks home+away."""
    c = (event.get("competitions") or [None])[0]
    if not c:
        return None
    home = next((x for x in c.get("competitors", []) if x.get("homeAway") == "home"), None)
    away = next((x for x in c.get("competitors", []) if x.get("homeAway") == "away"), None)
    if not home or not away:
        return None
    headline = (c.get("notes") or [{}])[0].get("headline", "")
    state = c.get("status", {}).get("type", {}).get("state", "")
    m = re.search(r"Game (\d+)", headline)
    return {
        "league": league,
        "date": datetime.fromisoformat(event["date"].replace("Z", "+00:00")).astimezone(),
        "home": home["team"]["abbreviation"],
        "home_name": home["team"].get("name", ""),
        "away": away["team"]["abbreviation"],
        "away_name": away["team"].get("name", ""),
        "home_score": _safe_int(home.get("score")),
        "away_score": _safe_int(away.get("score")),
        "winner": next((x["team"]["abbreviation"] for x in c["competitors"] if x.get("winner")), None),
        "final": state == "post",
        "in_progress": state == "in",
        "status_detail": c.get("status", {}).get("type", {}).get("shortDetail", ""),
        "round": round_num(headline),
        "game_num": int(m.group(1)) if m else None,
        "series_done": (c.get("series") or {}).get("completed", False),
    }


def normalize_placeholders(games):
    """Translate 'Lakers/Rockets' to 'LAL/HOU', then resolve to actual winner once that R1 series is decided."""
    name_map = {}
    for g in games:
        if "/" not in g["home"] and g["home_name"]:
            name_map[g["home_name"]] = g["home"]
        if "/" not in g["away"] and g["away_name"]:
            name_map[g["away_name"]] = g["away"]

    def fix(abbrev):
        if "/" not in abbrev: return abbrev
        return "/".join(name_map.get(p, p) for p in abbrev.split("/"))

    for g in games:
        g["home"] = fix(g["home"])
        g["away"] = fix(g["away"])

    wins_by_pair = defaultdict(lambda: defaultdict(int))
    for g in games:
        if "/" not in g["home"] and "/" not in g["away"] and g["final"] and g["winner"]:
            wins_by_pair[frozenset({g["home"], g["away"]})][g["winner"]] += 1
    winners = {key: team for key, wins in wins_by_pair.items()
               for team, count in wins.items() if count >= 4}
    for g in games:
        for slot in ("home", "away"):
            if "/" in g[slot]:
                parts = frozenset(g[slot].split("/"))
                if parts in winners:
                    g[slot] = winners[parts]
    return games


def _is_valid(g):
    return g["round"] > 0 and g["home"] and g["away"] and g["home"] != g["away"]


def gather(today):
    """Fetch one date-range request per league in parallel, parse, filter, normalize.

    Returns (games, network_ok). network_ok is False if any league fetch failed.
    """
    last = today + timedelta(days=LOOKAHEAD_DAYS)
    range_str = f"{PLAYOFF_START:%Y%m%d}-{last:%Y%m%d}"
    games = []
    network_ok = True
    with ThreadPoolExecutor(max_workers=len(LEAGUES)) as ex:
        futures = []
        for label, sport, lg in LEAGUES:
            url = ESPN.format(sport=sport, league=lg) + f"?dates={range_str}&seasontype=3"
            futures.append((label, ex.submit(fetch, url)))
        for label, future in futures:
            events = future.result()
            if events is None:
                network_ok = False
                continue
            for ev in events:
                p = parse(ev, label)
                if p is not None:
                    games.append(p)
    games = [g for g in games if _is_valid(g)]
    games = normalize_placeholders(games)
    return [g for g in games if _is_valid(g)], network_ok


def fmt_clock(dt):
    h = dt.hour % 12 or 12
    return f"{h}:{dt.minute:02d} {'PM' if dt.hour >= 12 else 'AM'}"


def fmt_when(g, today):
    gnum = f"G{g['game_num']}"
    if g["in_progress"]: return f"{gnum} live"
    d = g["date"].date()
    if d == today: return f"{gnum} {fmt_clock(g['date'])}"
    if d == today + timedelta(days=1): return f"{gnum} tomorrow"
    return f"{gnum} {d:%b} {d.day}"


def count_wins(series_games):
    """Returns (a, b, wins_a, wins_b) with (a, b) sorted alphabetically. Safe on empty/degenerate input."""
    if not series_games:
        return None, None, 0, 0
    finished = [g for g in series_games if g["final"]]
    sample = finished[0] if finished else series_games[0]
    teams = sorted({sample["home"], sample["away"]})
    if len(teams) != 2:
        return (teams[0] if teams else None), None, 0, 0
    a, b = teams
    if not finished:
        return a, b, 0, 0
    wins = defaultdict(int)
    for g in finished:
        if g["winner"]: wins[g["winner"]] += 1
    return a, b, wins[a], wins[b]


def is_series_done(series_games):
    """Series is done when one team has 4 wins, regardless of ESPN's series_done flag."""
    _, _, aw, bw = count_wins(series_games)
    return max(aw, bw) >= 4


def fmt_state(a, b, aw, bw):
    if aw == 0 and bw == 0: return ""
    if aw == bw: return f"tied {aw}-{bw}"
    return f"{a if aw > bw else b} {max(aw,bw)}-{min(aw,bw)}"


def elim_star(series_games):
    """Compact ★ for series in elim state. Used in schedule and series cards."""
    _, _, aw, bw = count_wins(series_games)
    if max(aw, bw) >= 3: return st("★", "yellow")
    return ""


def elim_status_live(series_games, live_game):
    """Expanded marker for live elim games: closeout (leader winning), stay alive (trailer winning), G7."""
    a, b, aw, bw = count_wins(series_games)
    if max(aw, bw) < 3: return ""
    if aw == bw == 3: return st("★ G7", "yellow")
    leader = a if aw > bw else b
    if live_game["home_score"] == live_game["away_score"]:
        return st("★", "yellow")
    leader_is_home = leader == live_game["home"]
    leader_winning = (live_game["home_score"] > live_game["away_score"]) == leader_is_home
    if leader_winning: return st("★ closeout", "yellow")
    return st("★ stay alive", "green")


def render_live(live_games, series_dict):
    if not live_games: return
    print(st("LIVE NOW", "bold"))
    for g in sorted(live_games, key=lambda g: abs(g["home_score"] - g["away_score"])):
        key = (g["league"], frozenset({g["home"], g["away"]}))
        a, b, aw, bw = count_wins(series_dict[key])
        ss = fmt_state(a, b, aw, bw)
        score = f"{g['away']} {st(str(g['away_score']), 'bold')} @ {g['home']} {st(str(g['home_score']), 'bold')}"
        score_visible = f"{g['away']} {g['away_score']} @ {g['home']} {g['home_score']}"
        pad = " " * max(0, COL_SCORE - len(score_visible))
        star = elim_status_live(series_dict[key], g)
        ctx = f"G{g['game_num']}" + (f" {star}" if star else "") + (f"  {ss}" if ss else "")
        print(f"  {g['league']}  {score}{pad}  {g['status_detail']:{COL_STATUS}}  {ctx}")


def find_recent_games(games_all, now):
    """Walk back through completed games newest-first, stop at a >RECENT_GAP_HOURS gap."""
    completed = sorted(
        [g for g in games_all if g["final"] and g["winner"] and g["date"] <= now],
        key=lambda g: g["date"], reverse=True,
    )
    if not completed: return []
    recent = [completed[0]]
    for g in completed[1:]:
        gap = (recent[-1]["date"] - g["date"]).total_seconds() / 3600
        if gap > RECENT_GAP_HOURS: break
        recent.append(g)
    return recent


def render_recent(games_all, series_dict, now):
    recent = find_recent_games(games_all, now)
    if not recent: return False
    print(st("RECENT", "bold"))
    for g in recent:
        key = (g["league"], frozenset({g["home"], g["away"]}))
        through = [s for s in series_dict[key] if s["final"] and s["date"] <= g["date"]]
        a, b, aw, bw = count_wins(through)
        if max(aw, bw) >= 4:
            winner = a if aw > bw else b
            note = f"{winner} advances {max(aw,bw)}-{min(aw,bw)}"
        elif aw == bw:
            note = f"tied {aw}-{bw}"
        else:
            note = f"{a if aw > bw else b} {max(aw,bw)}-{min(aw,bw)}"
        hrs = (now - g["date"]).total_seconds() / 3600
        ago = f"{int(hrs)}h ago" if hrs >= 1 else "just now"
        score = f"{g['away']} {g['away_score']} @ {g['home']} {g['home_score']}"
        tag = f"R{g['round']} G{g['game_num']}"
        pad = " " * max(0, COL_SCORE - len(score))
        line = f"  {ago:{COL_AGO}}  {g['league']}  {tag:{COL_TAG_RECENT}}  {score}{pad}  {note}"
        if hrs > DIM_AGE_HOURS: line = st(line, "dim")
        print(line)
    return True


def contingent_tag(game, series_dict):
    """Returns 'if X wins' if game depends on an earlier non-final game in the same series."""
    key = (game["league"], frozenset({game["home"], game["away"]}))
    series_games = series_dict.get(key, [])
    a, b, aw, bw = count_wins(series_games)
    if max(aw, bw) < 3: return ""
    if not any(not g["final"] and g["date"] < game["date"] for g in series_games):
        return ""
    trailer = b if aw > bw else a
    return f"if {trailer} wins"


def render_schedule(title, games, series_dict):
    if not games: return
    print(st(title, "bold"))
    for g in sorted(games, key=lambda g: g["date"]):
        key = (g["league"], frozenset({g["home"], g["away"]}))
        star = elim_star(series_dict.get(key, [g]))
        tag_visible = f"R{g['round']} G{g['game_num']}"
        tag = tag_visible + (f" {star}" if star else "")
        pad = " " * max(0, COL_TAG - len(tag_visible) - (2 if star else 0))
        line = f"  {fmt_clock(g['date']):{COL_TIME}}  {g['league']}  {tag}{pad}  {g['away']} @ {g['home']}"
        cont = contingent_tag(g, series_dict)
        if cont: line += "    " + st(cont, "dim")
        print(line)


def render_active_card(games, today):
    a, b, aw, bw = count_wins(games)
    score = fmt_state(a, b, aw, bw)
    nxt = (next((g for g in games if g["in_progress"]), None)
           or next((g for g in games if not g["final"]), None))
    when = fmt_when(nxt, today) if nxt else ""
    star = elim_star(games) if nxt else ""
    when_full = when + (f" {star}" if star and when else "")
    when_visible_len = len(when) + (2 if star and when else 0)
    when_pad = " " * max(0, COL_WHEN - when_visible_len)
    seq = "·".join(g["winner"] for g in games if g["final"] and g["winner"])
    teams = f"{a} vs {b}"
    return f"  {teams:{COL_TEAMS}}  {score:{COL_STATE}}  {when_full}{when_pad}  {seq}".rstrip()


def render_done_summary(done_series_list):
    items = []
    for games in done_series_list:
        a, b, aw, bw = count_wins(games)
        winner, loser = (a, b) if aw > bw else (b, a)
        items.append(f"{winner}-{loser} {max(aw,bw)}-{min(aw,bw)}")
    items.sort()
    lines, cur = [], ""
    for item in items:
        sep = " · " if cur else ""
        if len(cur) + len(sep) + len(item) > DONE_LINE_MAX:
            lines.append(cur)
            cur = item
        else:
            cur += sep + item
    if cur: lines.append(cur)
    print(st(f"  done: {lines[0]}", "dim"))
    for line in lines[1:]:
        print(st(f"        {line}", "dim"))


def main():
    now = datetime.now(timezone.utc).astimezone()
    today = now.date()
    tomorrow = today + timedelta(days=1)

    print(st(f"PLAYOFFS  {today:%a %b} {today.day} {today.year}", "bold")
          + st(f"   updated {fmt_clock(now)} {now:%Z}", "dim") + "\n")

    games, network_ok = gather(today)
    if not games:
        if not network_ok:
            print("ESPN unreachable. Check the warnings above.")
        else:
            print("No playoff games in the configured window. Off-season, or PLAYOFF_START needs a bump.")
        return

    series = defaultdict(list)
    for g in games:
        series[(g["league"], frozenset({g["home"], g["away"]}))].append(g)
    for s in series.values():
        s.sort(key=lambda g: g["date"])

    done_keys = {key for key, s in series.items() if is_series_done(s)}

    def series_active(g):
        return (g["league"], frozenset({g["home"], g["away"]})) not in done_keys

    live_games = [g for g in games if g["in_progress"] and series_active(g)]
    today_upcoming = [g for g in games
                      if g["date"].date() == today and not g["in_progress"] and not g["final"]
                      and series_active(g)]
    tomorrow_games = [g for g in games if g["date"].date() == tomorrow and series_active(g)]

    render_live(live_games, series)
    if live_games:
        print()
    elif render_recent(games, series, now):
        print()
    render_schedule("LATER TODAY", today_upcoming, series)
    if today_upcoming: print()
    render_schedule("TOMORROW", tomorrow_games, series)

    by_round = defaultdict(lambda: {"active": [], "done": []})
    for s in series.values():
        bucket = "done" if is_series_done(s) else "active"
        by_round[(s[-1]["league"], s[-1]["round"])][bucket].append(s)

    for league, rnd in sorted(by_round.keys(), key=lambda k: (LEAGUE_ORDER[k[0]], -k[1])):
        active = by_round[(league, rnd)]["active"]
        done = by_round[(league, rnd)]["done"]
        parts = []
        if active: parts.append(f"{len(active)} active")
        if done: parts.append(f"{len(done)} done")
        suffix = f" ({' · '.join(parts)})" if parts else ""
        print()
        print(st(f"{league} {ROUND_LABEL.get(rnd, 'Playoffs')}", "bold", "cyan") + suffix)
        for s in active:
            print(render_active_card(s, today))
        if done:
            render_done_summary(done)


if __name__ == "__main__":
    main()
