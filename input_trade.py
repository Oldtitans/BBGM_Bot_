from shared_info import serverExports
from shared_info import serversList
import pull_info
import basics
import discord
from discord.utils import get
import asyncio
import math
import shared_info
import random
async def input_trade(export, tradeData, message,actuallyinput = True):
    
    players = export['players']
    teams = export['teams']
    events = export['events']
    picks = export['draftPicks']
    #to start, let's just move the assets to their proper places
    #create this list again - tid, otherTid
    teamOne = None
    teamTwo = None
    for team, assets in tradeData.items():
        if teamOne == None:
            teamOne = int(team)
        else:
            teamTwo = int(team)
    tradeTeams = [[teamOne, teamTwo], [teamTwo, teamOne]]
    highestOvr = 0 #for making the news feed score
    dpids = []
    pids = [] #for the event
    if actuallyinput:
        for tid, otherTid in tradeTeams:
            for a in tradeData[tid]:
                #move these assets to the other team
                if a['type'] == 'draftPick': #draft pick
                    dpids.append(int(a['id']))
                    for dp in picks:
                        if dp['dpid'] == int(a['id']):
                            dp['tid'] = otherTid
                if a['type'] == 'player': #player
                    pids.append(int(a['id']))
                    for p in players:
                        if p['pid'] == int(a['id']):
                            if p['ratings'][-1]['ovr'] > highestOvr:
                                highestOvr = p['ratings'][-1]['ovr']
                            p['tid'] = otherTid
                            p['ptModifier'] = 1 #reset
                            transaction = {
                                "season": export['gameAttributes']['season'],
                                "phase": export['gameAttributes']['phase'],
                                "tid": otherTid,
                                "fromTid": tid,
                                "type": "trade"}
                            try:
                                p['transactions'].append(transaction)
                            except:
                                p['transactions'] = []
                                p['transactions'].append(transaction)
                            for t in teams:
                                if t['tid'] == tid:
                                    value = 1 / (1 + math.exp(-(30 * ((p['valueNoPot']/100) - 0.47))))
                                    if len(t['seasons']) > 0:
                                        t['seasons'][-1]['numPlayersTradedAway'] += value
        #now we'll make the event
        newEvent = {
            "type": "trade",
            "pids": pids,
            "tids": [teamTwo, teamOne],
            "dpids": dpids,
            "score": highestOvr - 50,
            "season": export['gameAttributes']['season'],
            "phase": export['gameAttributes']['phase'],
            "eid": events[-1]['eid']+1,
            "teams": []
        }
        for team, assets in tradeData.items():
            assetList = []
            for a in assets:
                if a['type'] == 'player':
                    for p in players:
                        if p['pid'] == int(a['id']):
                            ratingsIndex = len(p['ratings']) -1
                            statsIndex = len(p['stats']) -1
                    assetDict = {
                        "name": a['descrip'],
                        "pid": a['id'],
                        "ratingsIndex": ratingsIndex,
                        "statsIndex": statsIndex,
                        "contract": p['contract']
                    }
                if a['type'] == 'draftPick':
                    for dp in picks:
                        if dp['dpid'] == int(a['id']):
                            pickSeason = dp['season']
                            pickRound = dp['round']
                            pickOrigTid = dp['originalTid']
                    assetDict = {
                        "dpid": a['id'],
                        "season": pickSeason,
                        "round": pickRound,
                        "originalTid": pickOrigTid
                    }
                assetList.append(assetDict)
            newEvent['teams'].append({
                "assets": assetList
            })
        events.append(newEvent)
    #done! now send the transaction to channel
    text = '>>> **Trade**' + '\n' + '---' + '\n'
    teamNum = 0
    print(tradeData)
    for team, assets in tradeData.items():
        teamNum += 1
        for t in teams:
            if t['tid'] == int(team):
                teamName = t['region'] + ' ' + t['name']
                abbrev = t['abbrev']
        teamText = basics.team_mention(message, teamName, abbrev)
        if teamNum == 1:
            line = f"The {teamText} trade "
        if teamNum == 2:
            line += f" to the {teamText} for "
        added = 0
        for a in assets:
            if a['type'] == 'player':
                assetText = f"**{a['descrip']}**"
            if a['type'] == 'draftPick':
                assetText = f"a {a['descrip']}"
            added += 1
            if added == 1:
                line += assetText
            else:
                if added == len(assets):
                    line += f" and {assetText}"
                else:
                    line += f', {assetText}'
        if added == 0:
            if random.random() < 0.25:
                line += "cash considerations"
            elif random.random() < 0.25:
                line += "a bag of chips"
            elif random.random() < 0.5:
                names = []
                for p in players:
                    for r in p['ratings']:
                        if r['ovr'] > 65:
                            names.append(p['firstName']+" "+p['lastName'])
                if len(names) > 0:
                    line += "an autographed "+random.sample(names,1)[0] +" jersey"
                else:
                    line += "an autographed jersey"
            elif random.random() < 0.75:
                line += "weekly sales and marketing lessons"
            else:
                line += " nothing"
        if teamNum == 2:
            line += '.'
    text += line + '\n' + '---'
    errorSent = False
    channelId = int(str(serversList[str(message.guild.id)]['tradeannouncechannel']).replace('<#', '').replace('>', ''))
    channel = shared_info.bot.get_channel(channelId)
    if isinstance(channel, discord.TextChannel):
        # Send the message to the channel
        await channel.send(text)
    else:
        if errorSent == False:
            message.channel.send('Your trade channel is invalid, so signings were not sent. The trade was still executed.')
            errorSent = True
    

    #update export
    if actuallyinput:
        await basics.save_db(export, f'exports/{message.guild.id}-export.json')
    return newEvent['eid']
