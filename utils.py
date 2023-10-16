
import pickle
import json
from ytmusicapi import YTMusic
from datetime import datetime, timedelta
from time import strftime, gmtime
from fuzzywuzzy import fuzz, process
import musicbrainzngs
import sys
import re
import contextlib

from recordingDate import recurse_relations

# perform the YT search and return the (hopefully) best result
def searchYT(config, ytmusic, query, type, title, artist, duration, ignoredArtists, ignoredPhrases):
    wordRatio = config['DEFAULT'].getint('wordRatio')
    phraseRatio = config['DEFAULT'].getint('phraseRatio')
    aRatio = wordRatio if len(artist.split(' ')) == 1 else phraseRatio
    difference = 100

    results = ytmusic.search(query, type, None, 50)
    # make sure we got some results
    if results:
        # first make sure the matches are close
        matchingSongs = filterSongs(results, [('title', title, phraseRatio), ('artists', artist, aRatio)], 'title', False, True)
        currentSong = {}

        # again make sure there is something to work with
        if matchingSongs:
            # return the song with the duration that is closest to the original song
            for song in matchingSongs:
                d = song.get('duration')
                if any(x for x in song['artists'] for y in ignoredArtists if x['name'].find(y) != -1):
                    continue
                if [x for x in ignoredPhrases if x in song.get('title')]:
                    print(f'Skipping result: {song.get("title")} by {song.get("artist")}')
                    continue
                if not d:
                    continue
                t = datetime.strptime(d, '%M:%S')
                matchDuration = timedelta(minutes=t.minute, seconds=t.second)
                diff = abs(matchDuration.seconds - duration)
                if diff < difference:
                    difference = diff
                    currentSong = song
    # only return match with smallest duration difference
    return currentSong if difference <= 10 else False

# return only songs that closely match the title and artist
def filterSongs(songList, checks, key, oneResult, matchAll):
    if oneResult:
        return next((element for element in songList if keyCheck(checks, element, matchAll) if key in element), False)
    else:
        return [element for element in songList if keyCheck(checks, element, matchAll) if key in element] or False

# check multiple keys against values with given ratio.
# return one boolean result with AND/OR depending on matchAll
def keyCheck(checks, item, matchAll):
    bools = []
    for key, value, ratio in checks:
        if not item.get(key):
            continue
        if isinstance(item[key], (list, dict)):
            temp = process.extractOne(value, [(a['name'] if ('name' in a) else a) for a in [item[key]]], scorer=fuzz.token_set_ratio)
            if temp:
                match, r = temp
                b = (r >= ratio)
                bools.append(b)
        else:
            bools.append(fuzz.token_set_ratio(item[key].lower(), value.lower()) >= ratio)
    return all(bools) if matchAll else any(bools)

# check if the cache file is old
def isOld(fileName):
    fileDate = datetime.fromtimestamp(fileName.stat().st_mtime)
    oneDay = datetime.now() - timedelta(days=1)
    return fileDate < oneDay

# return a boolean from user input
def proceed(prompt):
    choices = {'y': True, 'n':False}
    while True:
        choice = input(f'{prompt} (Y/N)')
        if choice.lower() not in choices.keys():
            print('Invalid choice. Please enter "Y", or "N"')
        else:
            return choices[choice.lower()]

# simple function to print multiple songs, one per line
def printSongs(header, songs):
    print(header)
    aKey = 'artist' if 'artist' in songs[0].keys() else 'artists'
    for song in songs:
        title = song['title'] if 'title' in song.keys() else ''
        artist = song[aKey][0]['name'] if aKey in song.keys() else 'Unknown'
        album = song['album']['name'] if 'album' in song.keys() and song['album'] else 'Unknown'
        print(f'"{title}" BY: {artist} ON: {album}')

# process user query string and perform a fuzzy match unless exact is True
def performQuery(config, query, collection, exact):
    wordRatio = config['DEFAULT'].getint('wordRatio')
    phraseRatio = config['DEFAULT'].getint('phraseRatio')
    aKey = 'artist' if 'artist' in collection[0].keys() else 'artists'
    checks = []
    matchAll = True

    # field restricted matching
    if any(':' in s for s in query):
        for i in query:
            key, value = i.split(':')
            key = aKey if key == 'artist' else key
            # stricter matching for one word queries
            ratio = wordRatio if len(value.split(' ')) == 1 else phraseRatio
            if exact:
                ratio = 100
            checks.append((key, value, ratio))
    # simple match string
    else:
        matchAll = False
        value = ' '.join(query)
        # stricter matching for one word queries
        ratio = wordRatio if len(query) == 1 else phraseRatio
        if exact:
            ratio = 100
        for key in ['title', aKey, 'album']:
            checks.append((key, value, ratio))

    return filterSongs(collection, checks, 'title', False, matchAll)

# get the release year and the genres for one song from MusicBrainz
def getMBinfo(config, title, artist, videoId):
    wordRatio = config['DEFAULT'].getint('wordRatio')
    phraseRatio = config['DEFAULT'].getint('phraseRatio')
    relation_type = None
    aRatio = wordRatio if len(artist.split(' ')) == 1 else phraseRatio
    # set oldest release year to 0 so it is an int for matching later

    results = musicbrainzngs.search_recordings(limit=25, artist=artist,recording=title)['recording-list']

    # return the first match that definitely has the same artist and title
    song = filterSongs(results, [('title', title, phraseRatio), ('artist-credit', artist, aRatio)], 'length', True, True)
    if not song:
        return None
    oldest_release = song if song.get('year') else {'year': 2023}
    # get the earliest release date for a song instead of its re-release date
    (oldest_release, relation_type) = recurse_relations(song['id'], oldest_release, relation_type)
    # track itself contains genres or folksonomy tags as MusicBrainz calls them
    if 'tag-list' in song:
        tagList = [t['name'] for t in song['tag-list']]
    # track is missing genres, so check for them in all albums that match the artist (no various artist compilations)
    elif 'release-list' in song:
        tagList = [[t['name'] for t in a['tag-list']] for a in song['release-list'] if 'artist-credit' not in a if 'tag-list' in a]
    # give up already
    else:
        tagList = []
    return {'videoId': videoId, 'duration': song['length'], 'year': oldest_release['year'], 'genres': tagList, 'mbID': song['id']}


# return the set of rules for the playlist
def getRule(ruleSection):
    rule = {}
    start, end = None, None
    if 'year' in ruleSection.keys():
        # year = re.sub(r'\w', '', ruleSection['year'])
        year = ruleSection['year']
        # split year ranges into start and end. If there is one year make it the start,
        # and if there is a list of years
        if ',' in year:
            rule['year'] = [int(y) for y in list(year.split(','))]
        elif '-' in year:
            start, end = year.split('-')
        else:
            start, end = (year, None)
        # convert start and if present end to a list of years in the range
        if start:
            rule['year'] = list(range(int(start), int(end) + 1)) if end else list(int(start))
    if 'genre' in ruleSection.keys():
        temp = json.loads(ruleSection['genre'])
        rule['genre'] = [r for r in temp if not r.startswith('^')]
        # genres preceeded with ^ are negative genres. also, remove the ^ for easier matching later
        rule['notGenre'] = [r.replace('^', '') for r in temp if r.startswith('^')]
    return rule

@contextlib.contextmanager
def openFile(filename, mode='r'):
    try:
        f = open(filename, mode)
    except Exception as err:
        yield None, err
    else:
        try:
            yield f, None
        finally:
            f.close()
