import xlrd
import glob
import re
import json
import datetime
import os
from collections import namedtuple
from operator import attrgetter
from itertools import groupby

TESTING = True
COUNT_CROSS_DIVISION_GAMES = True  # reminder to remove this next year if needed. B8-D1_LEE DISTRICT_MCMINN changed divisions.
SKIP_RECENT_GAMES = True # used throughout the season to avoid counting games in the past day or two
CLUB_CLEAN_FOR_2023 = True

ExcelRow = namedtuple('ExcelRow', 'db_id, date, team, opponent, points, against')
Team = namedtuple('Team', 'team_id, division, club, coach')
Game = namedtuple('Game', 'game_id, date, team, opponent, points, against, result, win, lost, tie, source, cross_division')
Results = namedtuple('Results', 'divisions, teams, games')
WinPercent = namedtuple('WinPercent', 'team_id, percent, no_games')
Rank = namedtuple('Rank', 'team_id, rank, details')

LOTTERY_PICKS = {
    'FORT BELVOIR': 1,
    'SYC': 2,
    'MANASSAS PARK': 3,
    'LEE DISTRICT': 4,
    'FPYC': 5,
    'RESTON': 6,
    'MCLEAN': 7,
    'FORT HUNT': 8,
    'VYI': 9,
    'GAINESVILLE': 10,
    'BURKE': 11,
    'SOUTHWESTERN': 12,
    'SOUTH COUNTY': 13,
    'ARLINGTON': 14,
    'HERNDON': 15,
    'DYS': 16,
    'CYA': 17,
    'MT. VERNON': 18,
    'BRYC': 19,
    'FALLS CHURCH': 20,
    'LEE MT. VERNON': 21,
    'ANNANDALE': 22,
    'TURNPIKE': 23,
    'GREAT FALLS': 24,
    'GUM SPRINGS': 25,
}

DIVISION_PLAYOFF_SPOTS = {
    'B5-D1': 9,
    'B5-D2': 9,
    'B6-D1': 8,
    'B6-D2': 12,
    'B7-D1': 10,
    'B7-D2': 12,
    'B8-D1': 8,
    'B8-D2': 9,
    'B8-D3': 9,
    'G5-D1': 9,
    'G6-D1': 5,
    'G6-D2': 6,
    'G7-D1': 7,
    'G7-D2': 6,
    'G8-D1': 9,
    'G8-D2': 7,
}


def clean_column(original):
    return str(original).replace('"', '').strip()


def clean_number(original):
    stripped = clean_column(original)
    return round(float(stripped)) if stripped else 0


def find_excel(directory="./"):
    """ Find the excel report. """
    fcybl_files = glob.glob('{}/{}'.format(directory, './FCYBL*.xlsx'))
    if (len(fcybl_files) != 1):
        raise RuntimeError("Expected to find 1 FCYBL file, but found the following: {}".format(fcybl_files))
    return fcybl_files[0]


def read_excel(excel):
    rows = []
    workbook = xlrd.open_workbook(excel)
    worksheet = workbook.sheet_by_index(0)
    for curr_row in range(worksheet.nrows):
        if(curr_row == 0):
            continue  # do not need headers
        raw_date = datetime.datetime(*xlrd.xldate_as_tuple(worksheet.cell_value(curr_row, 1), workbook.datemode))
        yesterday = datetime.datetime.now() - datetime.timedelta(days = 1)
        if(SKIP_RECENT_GAMES and raw_date > yesterday):
            continue # future game
        date = raw_date.strftime('%Y-%m-%d')
        team = clean_column(worksheet.cell_value(curr_row, 4))
        opponent = clean_column(worksheet.cell_value(curr_row, 7))
        if(not opponent):
            continue # not a real game
        points = clean_number(worksheet.cell_value(curr_row, 10))
        points = 0 if not points else points
        against = clean_number(worksheet.cell_value(curr_row, 11))
        against = 0 if not against else against
        db_id = clean_number(worksheet.cell_value(curr_row, 12))
        row = ExcelRow(db_id, date, team, opponent, points, against)
        rows.append(row)
    return rows


def build_team(raw):
    if(CLUB_CLEAN_FOR_2023):
        raw = raw.replace("Fort Hunt G5-1Mathes", "Fort Hunt G5-1 Mathes")
        raw = raw.replace("Arlington G  Sedor", "Arlington G7-1 Sedor")
        raw = raw.replace("Reston G7 Altamirano", "Reston G7-2 Altamirano")
    parts = raw.split(">")
    division = clean_column(parts[2]).upper().replace("BOYS ", "B").replace("GIRLS ", "G").replace("TH GRADE DIVISION ", "-D")
    t_raw = clean_column(parts[3]).upper().replace("*", " ").replace("+", " ").replace("  ", " ")
    m = re.match(r"(.+) +[BG][0-9][- ]+[0-9]? +(.+)", t_raw)
    club = clean_column(m.group(1))
    coach = clean_column(m.group(2))
    team_id = "{}_{}_{}".format(division, club, coach)
    team = Team(team_id, division, club, coach)
    return team


def build_games(t1, t2, row):
    # default as loss for both teams if score isn't entered
    score_not_entered = row.points == 0 and row.against == 0
    cross_division = t1.division != t2.division
    if(score_not_entered):
        t1_game = Game(row.db_id, row.date, t1.team_id, t2.team_id, row.points, row.against, "L", False, True, False, True, cross_division)
        t2_game = Game(row.db_id, row.date, t2.team_id, t1.team_id, row.against, row.points, "L", False, True, False, False, cross_division)
        return (t1_game, t2_game)
    # determine win/loss/tie if there is a score
    t1_wins = row.points > row.against
    t1_loses = row.points < row.against
    t1_ties = row.points == row.against
    t1_result = "W" if t1_wins else "L" if t1_loses else "T"
    t2_result = "W" if t1_loses else "L" if t1_wins else "T"
    # the source (true/false) shows which was from the original excel source
    t1_game = Game(row.db_id, row.date, t1.team_id, t2.team_id, row.points, row.against, t1_result, t1_wins, t1_loses, t1_ties, True, cross_division)
    t2_game = Game(row.db_id, row.date, t2.team_id, t1.team_id, row.against, row.points, t2_result, t1_loses, t1_wins, t1_ties, False, cross_division)
    return (t1_game, t2_game)


def build_teams_and_games(rows):
    teams = []
    games = []
    for r in rows:
        if CLUB_CLEAN_FOR_2023:
            if "Delete Division" in r.team or "Delete Division" in r.opponent:
                continue
        t1 = build_team(r.team)
        t2 = build_team(r.opponent)
        teams.append(t1)
        teams.append(t2)
        g_tuple = build_games(t1, t2, r)
        games.append(g_tuple[0])
        games.append(g_tuple[1])
    teams = sorted(set(teams))
    divisions = sorted(set([t.division for t in teams]))
    return Results(divisions, teams, games)


def calculate_win_percent(games, team, group):
    """ Calculated the winning percentage against other teams in group """
    opponent_teams = [t.team_id for t in group]
    games_that_count = [g for g in games if g.team == team.team_id and g.opponent in opponent_teams]
    if(games_that_count):
        winning_games = [g for g in games_that_count if g.win]
        tie_games = [g for g in games_that_count if g.tie]
        percent = (len(winning_games) + (len(tie_games) * 0.5)) / len(games_that_count)
        return WinPercent(team.team_id, '{0:.3f}'.format(percent), False)
    else:
        return WinPercent(team.team_id, '{0:.3f}'.format(0.5), True)  # No Games different


def rank(games, group, start, mapping, all_teams, level):

    rankings = []

    # make sure everything is passed
    if(not(games and group and start)):
        raise RuntimeError("Required: games, group, and start")

    # initialize mapping if not found
    for t in group:
        if(not t.team_id in mapping):
            mapping[t.team_id] = []

    # only one team, so add it to the rankings
    if (len(group) == 1):
        team = group[0]
        rankings.append(Rank(team.team_id, start, mapping[team.team_id]))

    # multiple teams - need to compare them by winning percentage with lottery tie breaker
    else:

        # calculate winning percentage against the group
        group_percents = []
        for team in group:
            if(COUNT_CROSS_DIVISION_GAMES and level == 0):
                # One team changed divisions in the middle of the year. For iteration 1, need to compare against all teams.
                group = all_teams
            win_percent = calculate_win_percent(games, team, group)
            if(win_percent.no_games):
                mapping[team.team_id].append("-----")
            else:
                mapping[team.team_id].append(win_percent.percent)
            group_percents.append(win_percent)

        # group into common winning percentages
        group_percents.sort(key=attrgetter('percent'), reverse=True)  # highest percent to lowest
        split_groups = groupby(group_percents, attrgetter('percent'))
        split_list = [(sp, list(sts)) for sp, sts in split_groups]

        # if we are left with a single split group, it means they cannot be broken down further - go to lottery
        if(len(split_list) == 1):
            # no change to the group size from original (all same percent) - go to lottery
            split_teams = split_list[0][1]
            split_percents = []
            for t in split_teams:
                team_club = t.team_id.split("_")[1]
                win_percent = WinPercent(t.team_id, LOTTERY_PICKS[team_club], False)
                split_percents.append(win_percent)
            split_percents.sort(key=attrgetter('percent'))  # lowest lottery to highest
            for sp in split_percents:
                mapping[sp.team_id].append(sp.percent)
                rankings.append(Rank(sp.team_id, start, mapping[sp.team_id]))
                start += 1

        # we have multiple groups - run this recursively
        else:
            for sp, split_teams in split_list:
                ranks = rank(games, split_teams, start, mapping, all_teams, level + 1)
                rankings.extend(ranks)
                start += len(split_teams)

    return rankings


def build_rankings(results):
    rankings = []
    for division in results.divisions:
        teams = [t for t in results.teams if t.division == division]
        ranks = rank(results.games, teams, 1, {}, results.teams, 0)
        rankings.extend(ranks)
    return rankings


def calculate_record(team, games):
    team_games = [g for g in games if g.team == team.team_id]
    if(not COUNT_CROSS_DIVISION_GAMES):
        team_games = [g for g in team_games if not g.cross_division]
    wins = [g for g in team_games if g.win]
    losses = [g for g in team_games if g.lost]
    ties = [g for g in team_games if g.tie]
    return "{}-{}-{}".format(len(wins), len(losses), len(ties))


def print_to_json(results, rankings, excel):
    team_list = []
    games_list = []
    rankings_list = []
    for t in results.teams:
        t_dict = t._asdict()
        t_dict['record'] = calculate_record(t, results.games)
        team_list.append(t_dict)
    for g in results.games:
        games_list.append(g._asdict())
    for r in rankings:
        rankings_list.append(r._asdict())
    object = {
        'excel': os.path.basename(excel),
        'run_date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'divisions': results.divisions,
        'teams': team_list,
        'games': games_list,
        'lottery': LOTTERY_PICKS,
        'spots': DIVISION_PLAYOFF_SPOTS,
        'rankings': rankings_list
    }
    output = "var _MASTER_DATA = " + json.dumps(object, indent=2) + ";"
    log(output)


def log(message):
    print(message)

def test():
    excel = find_excel()
    rows = read_excel(excel)
    results = build_teams_and_games(rows)
    for r in results:
        print(r)
    #rankings = build_rankings(results)
    #print_to_json(results, rankings, excel)

    # for t in teams:
    #     games_for_team = [g for g in games if g.team == t.team_id and g.cross_division]
    #     if(games_for_team):
    #         print(t.team_id)
    #     for g in games_for_team:
    #         print("  {}".format(g.opponent))


def main():
    excel = find_excel()
    rows = read_excel(excel)
    results = build_teams_and_games(rows)
    rankings = build_rankings(results)
    print_to_json(results, rankings, excel)


if (__name__ == "__main__"):
    if TESTING:
        test()
    else:
        main()
