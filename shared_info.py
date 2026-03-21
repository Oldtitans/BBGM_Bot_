import json
import random
from datetime import datetime
commandsRaw = {}
commandAliases = {
    "r": "ratings",
    "s": "stats",
    "b": "bio",
    "setgm": "addgm",
    'phs':'hstats',
    'phstats':'hstats',
    "ts": "tstats",
    "tsp": 'ptstats',
    "rs": "resignings",
    "runrs": "runresignings",
    "ppr":"playoffpredict",
    "cs": "cstats",
    "hs": "hstats",
    'updateexport': 'updatexport',
    'update':'updatexport',
    "balance":"bal",
    "gl":"globalleaders",
    "l":"pleaders",
    'lp':'lotterypool',
    'mostuniform':'mostaverage',
    'inv':'inventory',
    'synergies':'synergy',
    'a':'mostaverage',
    'commands':'help',
    'bottom':'top'
}
iscrowded = False

modOnlyCommands = ['addrating','removetradepen','addredirect','removeredirect','removereleasedplayer','clearalloffers','edit', 'load', 'addgm', 'removegm', 'startdraft', 'runresignings', 'autocut', 'pausedraft','reprog','resetgamestrade','lottery','addrule','deleterule','addaward','removeaward']

curdate = datetime.today().strftime('%Y-%m-%d')

with open('servers.json') as f:
    serversList = json.load(f)

    serversList['default'].update({'rookieoptions':0.0})

with open('points.json') as f:
    points = json.load(f)
with open('daily.json') as f:
    daily = json.load(f) #daily is a list
with open('inventory.json') as f:
    inv = json.load(f)
serverExports = {}
trivias = dict()
triviabl = dict()

bot = None

def getadjective():
    adjlist = ['merrily','blissfully','stupidly','gladly','lazily','resignedly','reluctantly','calmly','smartly','affectionately','casually','haphazardly','accidentally','hastily','excitedly','normally','wishfully','hesitantly','sorrowfully','allegedly']
    adjlist += ['opportunistically','strategically','carefully','boldly','rashly','shrewdly']

    return random.sample(adjlist,1)[0]

embedFooter = 'Coded by ClevelandFan#2909 - Redistributed by Illusion'

