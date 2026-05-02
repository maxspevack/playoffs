"""Unit tests for playoffs.py logic helpers. Run with: python3 -m pytest tests/"""

from datetime import datetime, timedelta, timezone

import playoffs


def make_game(home="A", away="B", home_score=0, away_score=0, winner=None,
              final=False, in_progress=False, round_n=1, game_num=1,
              date_offset_hours=0, league="NHL", home_name=None, away_name=None,
              date_override=None):
    """Synthetic game dict matching parse() output shape."""
    return {
        "league": league,
        "date": date_override or datetime.now(timezone.utc).astimezone() + timedelta(hours=date_offset_hours),
        "home": home,
        "home_name": home_name if home_name is not None else home,
        "away": away,
        "away_name": away_name if away_name is not None else away,
        "home_score": home_score,
        "away_score": away_score,
        "winner": winner,
        "final": final,
        "in_progress": in_progress,
        "status_detail": "",
        "round": round_n,
        "game_num": game_num,
        "series_done": False,
    }


# ---------- _safe_int ----------

def test_safe_int_normal():
    assert playoffs._safe_int(5) == 5
    assert playoffs._safe_int("5") == 5


def test_safe_int_handles_none():
    assert playoffs._safe_int(None) == 0


def test_safe_int_handles_garbage():
    assert playoffs._safe_int("TBD") == 0
    assert playoffs._safe_int("") == 0
    assert playoffs._safe_int("abc") == 0


# ---------- count_wins ----------

def test_count_wins_empty_list():
    assert playoffs.count_wins([]) == (None, None, 0, 0)


def test_count_wins_no_finished_games():
    games = [make_game(home="A", away="B")]
    a, b, aw, bw = playoffs.count_wins(games)
    assert (a, b) == ("A", "B")
    assert (aw, bw) == (0, 0)


def test_count_wins_alphabetical_sort():
    games = [make_game(home="Z", away="A", final=True, winner="Z")]
    a, b, aw, bw = playoffs.count_wins(games)
    assert a == "A"
    assert b == "Z"
    assert aw == 0
    assert bw == 1


def test_count_wins_with_winners():
    games = [
        make_game(home="A", away="B", final=True, winner="A"),
        make_game(home="B", away="A", final=True, winner="A"),
        make_game(home="A", away="B", final=True, winner="B"),
    ]
    a, b, aw, bw = playoffs.count_wins(games)
    assert a == "A" and b == "B"
    assert aw == 2 and bw == 1


def test_count_wins_degenerate_same_team_safe():
    """If teams collapse to one (defensive), don't crash."""
    games = [make_game(home="A", away="A")]
    result = playoffs.count_wins(games)
    assert result[2] == 0
    assert result[3] == 0


# ---------- is_series_done ----------

def test_is_series_done_clinched():
    games = [make_game(final=True, winner="A") for _ in range(4)]
    assert playoffs.is_series_done(games) is True


def test_is_series_done_active():
    games = [make_game(final=True, winner="A") for _ in range(3)]
    assert playoffs.is_series_done(games) is False


def test_is_series_done_empty():
    assert playoffs.is_series_done([]) is False


def test_is_series_done_4_3():
    games = [make_game(final=True, winner="A") for _ in range(4)]
    games += [make_game(final=True, winner="B") for _ in range(3)]
    assert playoffs.is_series_done(games) is True


# ---------- round_num ----------

def test_round_num_first():
    assert playoffs.round_num("East 1st Round - Game 1") == 1
    assert playoffs.round_num("Western First Round - Game 3") == 1


def test_round_num_second():
    assert playoffs.round_num("East 2nd Round - Game 1") == 2
    assert playoffs.round_num("Conference Semifinals - Game 3") == 2


def test_round_num_conf_finals():
    assert playoffs.round_num("Eastern Conference Finals - Game 1") == 3
    assert playoffs.round_num("West Conf Finals - Game 4") == 3


def test_round_num_finals():
    assert playoffs.round_num("Stanley Cup Final - Game 1") == 4
    assert playoffs.round_num("NBA Finals - Game 1") == 4


def test_round_num_unknown():
    assert playoffs.round_num("") == 0
    assert playoffs.round_num("Regular Season Game") == 0
    assert playoffs.round_num("Play-In Tournament") == 0


# ---------- fmt_state ----------

def test_fmt_state_empty():
    assert playoffs.fmt_state("A", "B", 0, 0) == ""


def test_fmt_state_tied():
    assert playoffs.fmt_state("A", "B", 2, 2) == "tied 2-2"
    assert playoffs.fmt_state("A", "B", 3, 3) == "tied 3-3"


def test_fmt_state_a_leading():
    assert playoffs.fmt_state("A", "B", 3, 2) == "A 3-2"


def test_fmt_state_b_leading():
    assert playoffs.fmt_state("A", "B", 1, 2) == "B 2-1"


# ---------- elim_status_live ----------

def _series_3_2():
    """Series state: 5 games, A leads 3-2."""
    return [
        make_game(final=True, winner="A"),
        make_game(final=True, winner="A"),
        make_game(final=True, winner="A"),
        make_game(final=True, winner="B"),
        make_game(final=True, winner="B"),
    ]


def test_elim_status_live_no_elim_yet():
    games = [
        make_game(final=True, winner="A"),
        make_game(final=True, winner="B"),
    ]
    live = make_game(home="A", away="B", home_score=2, away_score=1, in_progress=True)
    assert playoffs.elim_status_live(games, live) == ""


def test_elim_status_live_closeout_leader_winning():
    games = _series_3_2()
    live = make_game(home="A", away="B", home_score=3, away_score=1, in_progress=True)
    assert "closeout" in playoffs.elim_status_live(games, live)


def test_elim_status_live_stay_alive_trailer_winning():
    games = _series_3_2()
    live = make_game(home="A", away="B", home_score=1, away_score=3, in_progress=True)
    assert "stay alive" in playoffs.elim_status_live(games, live)


def test_elim_status_live_g7_3_3():
    games = [make_game(final=True, winner="A") for _ in range(3)]
    games += [make_game(final=True, winner="B") for _ in range(3)]
    live = make_game(home="A", away="B", home_score=2, away_score=1, in_progress=True)
    assert "G7" in playoffs.elim_status_live(games, live)


def test_elim_status_live_tied_score_in_progress():
    games = _series_3_2()
    live = make_game(home="A", away="B", home_score=2, away_score=2, in_progress=True)
    result = playoffs.elim_status_live(games, live)
    assert "★" in result
    assert "closeout" not in result
    assert "stay alive" not in result


def test_elim_status_live_leader_is_away_winning():
    """Leader is on the away side and currently winning. Should be closeout."""
    games = _series_3_2()  # A leads 3-2
    live = make_game(home="B", away="A", home_score=1, away_score=3, in_progress=True)
    assert "closeout" in playoffs.elim_status_live(games, live)


# ---------- normalize_placeholders ----------

def test_normalize_placeholders_translates_names():
    games = [
        make_game(home="LAL", away="HOU", home_name="Lakers", away_name="Rockets"),
        make_game(home="Lakers/Rockets", away="OKC", home_name="Lakers/Rockets"),
    ]
    result = playoffs.normalize_placeholders(games)
    assert result[1]["home"] == "LAL/HOU"


def test_normalize_placeholders_resolves_winner():
    games = [make_game(home="A", away="B", final=True, winner="A", game_num=i+1) for i in range(4)]
    games.append(make_game(home="A/B", away="C", round_n=2))
    result = playoffs.normalize_placeholders(games)
    assert result[-1]["home"] == "A"


def test_normalize_placeholders_does_not_resolve_undecided():
    games = [
        make_game(home="A", away="B", final=True, winner="A", game_num=1),
        make_game(home="A/B", away="C", round_n=2),
    ]
    result = playoffs.normalize_placeholders(games)
    # Series not done (only 1 win for A), placeholder stays
    assert result[-1]["home"] == "A/B"


def test_normalize_placeholders_no_change_when_no_placeholders():
    games = [make_game(home="A", away="B")]
    result = playoffs.normalize_placeholders(games)
    assert result[0]["home"] == "A"
    assert result[0]["away"] == "B"


# ---------- find_recent_games ----------

def _now():
    return datetime.now(timezone.utc).astimezone()


def test_find_recent_games_empty():
    assert playoffs.find_recent_games([], _now()) == []


def test_find_recent_games_no_finished():
    games = [make_game(in_progress=True)]
    assert playoffs.find_recent_games(games, _now()) == []


def test_find_recent_games_within_gap():
    now = _now()
    games = [
        {**make_game(final=True, winner=str(i)),
         "date": now - timedelta(hours=h)}
        for i, h in enumerate([2, 4, 8, 14])
    ]
    recent = playoffs.find_recent_games(games, now)
    assert len(recent) == 4


def test_find_recent_games_stops_at_gap():
    now = _now()
    games = [
        {**make_game(final=True, winner="A"), "date": now - timedelta(hours=2)},
        {**make_game(final=True, winner="B"), "date": now - timedelta(hours=4)},
        {**make_game(final=True, winner="C"), "date": now - timedelta(hours=8)},
        {**make_game(final=True, winner="D"), "date": now - timedelta(hours=24)},  # 16h gap
    ]
    recent = playoffs.find_recent_games(games, now)
    winners = [g["winner"] for g in recent]
    assert winners == ["A", "B", "C"]


def test_find_recent_games_skips_no_winner():
    now = _now()
    games = [
        {**make_game(final=True, winner="A"), "date": now - timedelta(hours=2)},
        {**make_game(final=True, winner=None), "date": now - timedelta(hours=4)},
    ]
    recent = playoffs.find_recent_games(games, now)
    assert len(recent) == 1
    assert recent[0]["winner"] == "A"


# ---------- contingent_tag ----------

def test_contingent_tag_no_clinch_chance():
    """Series 1-0 with G2 tomorrow: not contingent (no team has 3 wins yet)."""
    today = _now()
    g1 = {**make_game(home="A", away="B", final=True, winner="A", game_num=1),
          "date": today - timedelta(days=1)}
    g2 = {**make_game(home="B", away="A", game_num=2),
          "date": today + timedelta(days=1)}
    series_dict = {("NHL", frozenset({"A", "B"})): [g1, g2]}
    assert playoffs.contingent_tag(g2, series_dict) == ""


def test_contingent_tag_pending_earlier_game():
    """Tomorrow G7 contingent on today's G6 outcome."""
    today = _now()
    series_games = []
    for i, w in enumerate(["A", "A", "A", "B", "B"]):
        series_games.append({
            **make_game(final=True, winner=w, game_num=i+1),
            "date": today - timedelta(days=10-i),
        })
    g6 = {**make_game(game_num=6), "date": today}
    g7 = {**make_game(game_num=7), "date": today + timedelta(days=1)}
    series_games.extend([g6, g7])
    series_dict = {("NHL", frozenset({"A", "B"})): series_games}
    # B trails 2-3, must win G6 to force G7
    assert "if B wins" in playoffs.contingent_tag(g7, series_dict)


def test_contingent_tag_no_earlier_pending():
    """Series tied 3-3 already, G7 confirmed, no contingency."""
    today = _now()
    series_games = [
        {**make_game(final=True, winner=w, game_num=i+1),
         "date": today - timedelta(days=10-i)}
        for i, w in enumerate(["A", "A", "A", "B", "B", "B"])
    ]
    g7 = {**make_game(game_num=7), "date": today + timedelta(days=1)}
    series_games.append(g7)
    series_dict = {("NHL", frozenset({"A", "B"})): series_games}
    assert playoffs.contingent_tag(g7, series_dict) == ""


# ---------- parse ----------

def test_parse_basic():
    event = {
        "date": "2026-05-01T23:00Z",
        "competitions": [{
            "competitors": [
                {"homeAway": "home", "team": {"abbreviation": "MTL", "name": "Canadiens"},
                 "score": "3", "winner": True},
                {"homeAway": "away", "team": {"abbreviation": "TB", "name": "Lightning"},
                 "score": "2", "winner": False},
            ],
            "notes": [{"headline": "East 1st Round - Game 6"}],
            "status": {"type": {"state": "post", "shortDetail": "Final"}},
            "series": {"completed": False},
        }]
    }
    parsed = playoffs.parse(event, "NHL")
    assert parsed["home"] == "MTL"
    assert parsed["away"] == "TB"
    assert parsed["winner"] == "MTL"
    assert parsed["round"] == 1
    assert parsed["game_num"] == 6
    assert parsed["final"] is True
    assert parsed["home_score"] == 3
    assert parsed["away_score"] == 2


def test_parse_handles_non_numeric_score():
    """Score field may be 'TBD' or empty for placeholder games."""
    event = {
        "date": "2026-05-01T23:00Z",
        "competitions": [{
            "competitors": [
                {"homeAway": "home", "team": {"abbreviation": "TBD", "name": "TBD"}, "score": "TBD"},
                {"homeAway": "away", "team": {"abbreviation": "TBD", "name": "TBD"}, "score": ""},
            ],
            "notes": [{"headline": "First Round - Game 1"}],
            "status": {"type": {"state": "pre"}},
        }]
    }
    parsed = playoffs.parse(event, "NBA")
    assert parsed["home_score"] == 0
    assert parsed["away_score"] == 0


def test_parse_no_notes():
    """Event with empty notes (regular-season leak through seasontype=3)."""
    event = {
        "date": "2026-04-15T23:00Z",
        "competitions": [{
            "competitors": [
                {"homeAway": "home", "team": {"abbreviation": "BUF", "name": "Sabres"}, "score": "0"},
                {"homeAway": "away", "team": {"abbreviation": "DAL", "name": "Stars"}, "score": "0"},
            ],
            "notes": [],
            "status": {"type": {"state": "pre"}},
        }]
    }
    parsed = playoffs.parse(event, "NHL")
    assert parsed["round"] == 0
    assert parsed["game_num"] is None


def test_parse_missing_winner_field():
    event = {
        "date": "2026-05-01T23:00Z",
        "competitions": [{
            "competitors": [
                {"homeAway": "home", "team": {"abbreviation": "A", "name": "A"}, "score": "1"},
                {"homeAway": "away", "team": {"abbreviation": "B", "name": "B"}, "score": "0"},
            ],
            "notes": [{"headline": "First Round - Game 1"}],
            "status": {"type": {"state": "in"}},
        }]
    }
    parsed = playoffs.parse(event, "NHL")
    assert parsed["winner"] is None


# ---------- fmt_when ----------

def test_fmt_when_in_progress():
    g = make_game(in_progress=True, game_num=6)
    assert playoffs.fmt_when(g, _now().date()) == "G6 live"


def test_fmt_when_today():
    today = _now().date()
    g = make_game(game_num=6, date_override=datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc).astimezone() + timedelta(hours=18))
    assert playoffs.fmt_when(g, today).startswith("G6 ")


def test_fmt_when_tomorrow():
    today = _now().date()
    tomorrow = today + timedelta(days=1)
    g = make_game(game_num=7, date_override=datetime.combine(tomorrow, datetime.min.time()).replace(tzinfo=timezone.utc).astimezone() + timedelta(hours=18))
    assert playoffs.fmt_when(g, today) == "G7 tomorrow"


def test_fmt_when_future_date():
    today = _now().date()
    later = today + timedelta(days=3)
    g = make_game(game_num=1, date_override=datetime.combine(later, datetime.min.time()).replace(tzinfo=timezone.utc).astimezone() + timedelta(hours=18))
    result = playoffs.fmt_when(g, today)
    assert result.startswith("G1 ")
    assert "tomorrow" not in result
