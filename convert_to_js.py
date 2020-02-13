import xlrd
import glob
import re
import json
import datetime
import os
from collections import namedtuple
from operator import attrgetter
from itertools import groupby


ExcelRow = namedtuple('ExcelRow', 'db_id, date, team, opponent, points, against')
Team = namedtuple('Team', 'team_id, division, club, coach')
Game = namedtuple('Game', 'game_id, date, team, opponent, points, against, result, win, lost, tie, source')
Results = namedtuple('Results', 'divisions, teams, games')
WinPercent = namedtuple('WinPercent', 'team_id, percent, no_games')
Rank = namedtuple('Rank', 'team_id, rank, details')

LOTTERY_PICKS = {
    'GREAT FALLS': 1,
    'MCLEAN': 2,
    'BRYC': 3,
    'BURKE': 4,
    'SYA': 5,
    'ANNANDALE': 6,
    'SOUTH COUNTY': 7,
    'VIENNA': 8,
    'TURNPIKE': 9,
    'MANASSAS PARK': 10,
    'GUM SPRINGS': 11,
    'LEE MT. VERNON': 12,
    'LEE-MT. VERNON': 12,
    'SPRINGFIELD': 13,
    'CYA': 14,
    'ARLINGTON': 15,
    'GAINESVILLE': 16,
    'SOUTH LOUDOUN': 17,
    'RESTON': 18,
    'FPYC': 19,
    'BAILEYS': 20,
    'BAILEYS CC': 20,
    'HERNDON': 21,
    'LEE DISTRICT': 22,
    'FALLS CHURCH': 23,
    'FORT HUNT': 24,
    'FORT BELVOIR': 25,
    'MT. VERNON': 26,
    'JAMES LEE': 27,
    'ALEXANDRIA': 28
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
        db_id = clean_number(worksheet.cell_value(curr_row, 12))
        team = clean_column(worksheet.cell_value(curr_row, 4))
        opponent = clean_column(worksheet.cell_value(curr_row, 7))
        points = clean_number(worksheet.cell_value(curr_row, 10))
        against = clean_number(worksheet.cell_value(curr_row, 11))
        if(not(team and opponent and (points or against))):
            continue  # not a real game (can be 0 if forfeit)
        date = datetime.datetime(*xlrd.xldate_as_tuple(worksheet.cell_value(curr_row, 1), workbook.datemode))
        date = date.strftime('%Y-%m-%d')
        if("2019" in date and "5TH" in team.upper()):
            continue  # skip pool play games
        row = ExcelRow(db_id, date, team, opponent, points, against)
        rows.append(row)
    return rows


def build_team(raw):
    parts = raw.split(">")
    division = clean_column(parts[2]).upper().replace("BOYS ", "B").replace("GIRLS ", "G").replace("TH GRADE DIVISION ", "-D")
    t_raw = clean_column(parts[3]).upper()
    m = re.match(r"(.+) +[BG][0-9][- ]+[0-9]? +(.+)", t_raw)
    club = clean_column(m.group(1))
    coach = clean_column(m.group(2))
    team_id = "{}_{}_{}".format(division, club, coach)
    team = Team(team_id, division, club, coach)
    return team


def build_games(t1, t2, row):
    t1_wins = row.points > row.against
    t1_loses = row.points < row.against
    t1_ties = row.points == row.against
    t1_result = "W" if t1_wins else "L" if t1_loses else "T"
    t2_result = "W" if t1_loses else "L" if t1_wins else "T"
    # the source (true/false) shows which was from the original excel source
    t1_game = Game(row.db_id, row.date, t1.team_id, t2.team_id, row.points, row.against, t1_result, t1_wins, t1_loses, t1_ties, True)
    t2_game = Game(row.db_id, row.date, t2.team_id, t1.team_id, row.against, row.points, t2_result, t1_loses, t1_wins, t1_ties, False)
    return (t1_game, t2_game)


def build_teams_and_games(rows):
    teams = []
    games = []
    for r in rows:
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


def rank(games, group, start, mapping, level=0):

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
                ranks = rank(games, split_teams, start, mapping, level + 1)
                rankings.extend(ranks)
                start += len(split_teams)

    return rankings


def build_rankings(results):
    rankings = []
    for division in results.divisions:
        teams = [t for t in results.teams if t.division == division]
        ranks = rank(results.games, teams, 1, {})
        rankings.extend(ranks)
    return rankings


def print_to_json(results, rankings, excel):
    team_list = []
    games_list = []
    rankings_list = []
    for t in results.teams:
        team_list.append(t._asdict())
    for g in results.games:
        games_list.append(g._asdict())
    for r in rankings:
        rankings_list.append(r._asdict())
    object = {
        'excel': os.path.basename(excel),
        'divisions': results.divisions,
        'teams': team_list,
        'games': games_list,
        'lottery': LOTTERY_PICKS,
        'rankings': rankings_list
    }
    output = "var _MASTER_DATA = " + json.dumps(object, indent=2) + ";"
    print(output)


def main():
    excel = find_excel()
    rows = read_excel(excel)
    results = build_teams_and_games(rows)
    rankings = build_rankings(results)
    print_to_json(results, rankings, excel)


if (__name__ == "__main__"):
    main()
