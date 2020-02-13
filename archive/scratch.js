angular.module('FCYBL', []).controller('RankingsController', ["$log", function ($log) {

    var my = this;
    my.master = _MASTER_DATA;
    my.divisions = my.master.divisions;
    my.teams = my.master.teams;
    my.games = my.master.games;
    my.lottery = my.master.lottery;
    my.rankings = my.master.rankings;

    my.showRankingsForDivision = function (division) {
        
    };
    
    rank();

}]);

angular.module('FCYBL', []).controller('RankingsController', ["$log", function ($log) {

    var my = this;
    my.master = _MASTER_DATA;
    my.gamesForTeam = [];
    my.ranking = [];

    /**
     * Find the winning percentage for the team against every other team.
     */
    function winPercent(team, teams) {
        var allGames = my.master.games.filter(game => game.team.team_id == team.team_id)
        var gamesThatCount = []
        allGames.forEach(game => {
            teams.forEach(function(them) {
              if(them.team_id == game.opponent.team_id) {
                  gamesThatCount.push(game);
              }
            });
        });
        if(gamesThatCount.length == 0) {
            return (0 / 1).toFixed(3);
        }
        var wins = gamesThatCount.filter(g => g.win);
        var percent = (wins.length / gamesThatCount.length).toFixed(3);
        return percent;
    }
    
    /**
     * Compare head-to-head, and then lottery.
     */
    function getLottery(team) {
        return _MASTER_DATA.lottery[team.club];
    }

    function rankTeams(teams, start, depth) {
        $log.info("DEPTH: " + depth + " = START: " + start);
        if(!teams || teams.length <= 0) {
            $log.error("Teams is empty.");
        } else if(teams.length == 1) {
            teams[0].finalRank = start;
        } else {
            // calculate winning percentage for each against teams in group and rank
            // todo - 3 way+ tie to lottery (unable to further break down groups)
            teams.forEach(t => {
                t.percent = winPercent(t, teams);
                t.ranks.push(t.percent);
            });
            teams.sort((a, b) => b.percent - a.percent) // alphanumeric
            groups = _.groupBy(teams, 'percent');
            groupPercents = _.keys(groups);
            $log.debug("groups");
            $log.debug(groups);
            if(groupPercents.length == 1) {
                groups[groupPercents[0]].forEach(t => {
                    t.finalRank = getLottery(t)
                });
            } else {
                $log.debug("more");
                groupPercents.forEach(groupPercent => {
                    $log.debug("START groupPercent: " + groupPercent);
                    $log.debug(groups);
                    var groupTeams = groups[groupPercent];
                    $log.debug(groupTeams);
                    $log.debug("about to call rankTeams again for groupPercent: " + groupPercent);
                    rankTeams(groupTeams, start, depth + 1);
                    start += groupTeams.length;
                    $log.debug("END groupPercent: " + groupPercent);
                    
                })
                $log.debug("done");
            }
            // group by percent
            // sort by percent groups
        }
    }
    
    function rank() {
        for(var i = 0; i < my.master.divisions.length; i++) {
            if(i != 1) { continue; }
            var current = my.ranking[i] = {};
            var division = my.master.divisions[i];
            current.division = division;
            var teams = my.master.teams.filter(team => team.division == division);
            teams.forEach(t => t.ranks = []);
            rankTeams(teams, 1, 1);
            current.teams = teams;
        }
        $log.debug(my.ranking[1].teams[9]);
        $log.debug(my.ranking[1]);
    }

    my.showGamesForTeam = function (team) {
        
    };
    
    rank();

}]);