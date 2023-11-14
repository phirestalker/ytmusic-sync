#!/usr/local/bin/python3

# author: Neal Piche

import sys
import os, subprocess, platform
import pathlib
import json
import pickle
import mutagen
import configparser
import ytmusicapi
from ytmusicapi import YTMusic
from datetime import datetime, timedelta
from time import strftime, gmtime, sleep
from appdirs import *
from tqdm import tqdm
import re
import csv
import musicbrainzngs

from utils import *
from fileOperations import *


appName = 'YT Music Sync'
appVer = '0.1'
YTDelay = None
wordRatio = None
phraseRatio = None
userDir = pathlib.Path(user_data_dir(appName, ''))
config = configparser.ConfigParser()
configPath = None
cacheFile = None
authFile = None
MBfile = None
ytmusic = None
uploadSongs = False
notFound = []
ignoredArtists = []
ignoredPhrases = []
firstArg = None
playlistItems = set()
MBdata = []
commandHelp = [
'Available commands are:',
'-d directory\tScans all subdirectories under directory for music files and adds them to library',
'-p playlist\tAdds all playlist items to library and to the named playlist',
'likes\tAdds all liked songs to your library',
'smart\tCreates and updates playlists by rules set in config file',
'config\tPerform config file operations',
'\tSubcommands:'
'\tedit\tOpens the config file for editing in your default editor',
'\treset\tResets the config file to default settings',
'resetAuth\tUse to delete auth file and paste new credentials',
'delete\t\tDeletes specified items'
]
deleteHelp = [
'Available delete subcommands are:\n',
'all\t\tdeletes everything from YT music!!',
'uploads\t\tdeletes all uploaded music',
'library\t\tdeletes all songs from your library',
'likes\t\tremove all songs from your likes',
'playlist\tremoves all playlists or specified playlist by name',
'query\t\tdelete items that match a query from uploads, library, and likes',
'\t\t\t-e option will perform and exact search instead of a fuzzy search',
'\t\t\tA string of words will match ALL words',
'\t\t\tartist:"query" will only search artist for "query"',
'\t\t\ttitle:"query" will only search song title for "query"',
'\t\t\talbum:"query" will only search album for "query"'
]

musicbrainzngs.set_useragent(
    'Youtube Music Sync',
    appVer,
    ''
)

# perform add to library, playlist, or uploads for each file
# filename: the full path to the file
# playlist: name of playlist to add track to
def processFile(filename):
    global notFound
    tRatio = phraseRatio

    try:
        track = mutagen.File(filename)
    except Exception as e:
        print(f'Mutagen could not process file ({filename})\n {e}')
    # skip damaged or non-audio file
    if not track:
        return False
    tmpArtist = track.get('artist')
    artist = tmpArtist[0].split(' feat.')[0] if tmpArtist else '' # truncate artist at feat. so only one artists name is present
    album = track['album'][0] if 'album' in track.keys() else ''
    title = track['title'][0] if 'title' in track.keys() else ''
    # get duration as a familiar M:S formated string
    duration = strftime("%M:%S", gmtime(track.info.length))

    # skip songs missing artist or title
    if not artist or not title:
        notFound.append({'title':title,'artist':artist,'duration':duration,'filename':filename})
        return False

    aRatio = wordRatio if len(artist.split(' ')) == 1 else phraseRatio
    # check library for song
    libraryResult = filterSongs(library, [('title', title, tRatio), ('artists', artist, aRatio)], 'title', True, True)
    if libraryResult:
        print(f'song "{title}" by {artist}: {duration} is already in your library')
        return libraryResult['videoId']
    # check uploads for song
    uploadsResult = filterSongs(uploads, [('title', title, tRatio), ('artist', artist, aRatio)], 'title', True, True)
    if uploadsResult:
        print(f'song "{title}" by {artist}: {duration} is already uploaded')
        return uploadsResult['videoId']
    # search YT music for the song
    song = searchYT(config, ytmusic, f'{artist} - {title}', 'songs', title, artist, track.info.length, ignoredArtists, ignoredPhrases)

    # if the song was found
    if song:
        print(f'Adding song "{song["title"]}" by {song["artists"][0]["name"]}: {song["duration"]} for "{title}" by {artist}: {duration} to library')
        # some songs are missing the necessary information to add them to your library
        # if the song has the info, add to library, and just like it if not
        if 'feedbackTokens' in song.keys():
            makeCall('library', song, False)
        else:
            makeCall('likes', song, False)
        return song['videoId']
    # song not found on YT music, so upload it
    elif uploadSongs:
        print(f'Uploading song "{title}" by {artist}: {duration}')
        response = makeCall('uploads', filename, False)
        print(response)
    # user does not want to upload the song
    else:
        print(f'MISSING "{title}" by {artist}: {duration}')
        notFound.append({'title':title,'artist':artist,'duration':duration,'filename':filename})
    return False

# load options from the ini file or create it with defaults if it doesn't exist
def loadConfig():
    global config
    global ignoredArtists
    global ignoredPhrases
    global cacheFile
    global firstArg
    global uploadSongs
    global authFile
    global MBfile
    global configPath
    global wordRatio
    global phraseRatio
    global YTDelay

    configPath = userDir / 'config.ini'
    if len(sys.argv) > 1:
        firstArg = sys.argv[1]

    if configPath.exists():
        print('loading config from file')
        config.read(configPath)
        # if the ini file contains a relative path for the cache file use userDir as a base
        cacheFile = pathlib.Path(config['DEFAULT']['cachefile']) if config['DEFAULT']['cachefile'].startswith('/') else userDir / config['DEFAULT']['cachefile']
        authFile = pathlib.Path(config['DEFAULT']['authfile']) if config['DEFAULT']['authfile'].startswith('/') else userDir / config['DEFAULT']['authfile']
        MBfile = pathlib.Path(config['DEFAULT']['mbfile']) if config['DEFAULT']['mbfile'].startswith('/') else userDir / config['DEFAULT']['mbfile']
        ignoredArtists = json.loads(config.get('DEFAULT', 'ignoredartists'))
        ignoredPhrases = json.loads(config.get('DEFAULT', 'ignoredphrases'))
        uploadSongs = config['DEFAULT'].getboolean('uploadsongs')
        wordRatio = config['DEFAULT'].getint('wordRatio')
        phraseRatio = config['DEFAULT'].getint('phraseRatio')
        YTDelay = config['DEFAULT'].getfloat('YTDelay')
        musicbrainzngs.set_hostname(config['DEFAULT']['mbhost'])
        musicbrainzngs.set_rate_limit(1, config['DEFAULT'].getfloat('mbrateLimit'))
    else:
        config['DEFAULT'] = {}
        config['DEFAULT']['cachefile'] = 'cache.p'
        config['DEFAULT']['authfile'] = 'headers_auth.json'
        config['DEFAULT']['mbfile'] = 'MBdata.p'
        config['DEFAULT']['uploadsongs'] = 'no'
        config['DEFAULT']['mbhost'] = 'musicbrainz.org'
        config['DEFAULT']['mbrateLimit'] = '1'
        config['DEFAULT']['wordRatio'] = '96'
        config['DEFAULT']['phraseRatio'] = '89'
        config['DEFAULT']['YTDelay'] = '0.1'
        config['DEFAULT']['approach'] = 'hybrid'
        config['DEFAULT']['ignoredartists'] = json.dumps(['karaoke', 'in the style of', 'tribute'])
        config['DEFAULT']['ignoredphrases'] = json.dumps(['karaoke', 'in the style of', 'tribute'])
        config['DEFAULT']['ignoredgenres'] = json.dumps(['^punk', '^grunge' ,'^hard', '^metal', '^classical', '^alternative', '^rap', '^hip hop', '^holiday', '^christmas'])
        cacheFile = userDir / 'cache.p'
        authFile = userDir / 'headers_auth.json'
        MBfile = userDir / 'MBdata.p'
        wordRatio = 96
        phraseRatio = 89
        YTDelay = 0.1
        ignoredArtists = ['karaoke', 'in the style of', 'tribute']
        ignoredPhrases = ['karaoke', 'in the style of', 'tribute']
        print('Writing config file')
        with openFile(configPath, 'w') as (configFile, err):
            if err:
                print(f'Problem saving config file: {err}')
            else:
                config.write(configFile)

def authenticate(reset = False):
    global ytmusic

    if reset:
        os.remove(authFile)
    if authFile.exists():
        ytmusic = YTMusic(str(authFile))
    else:
        ytmusicapi.setup(filepath=str(authFile))
        exit(0)

def myExceptHandler(exctype, value, traceback):
    # print 5 bells to signify error
    print('\a\a\a\a\a')
    saveCache(cacheFile, MBfile, MBdata, [uploads, library, playlists, likes])
    sys.__excepthook__(exctype, value, traceback)

def deletePlaylist(name):
    if not name:
        if proceed('This will delete ALL playlists from YT Music. Are you sure?'):
            for pls in playlists:
                ytmusic.delete_playlist(pls['playlistId'])
                sleep(YTDelay)
    else:
        name = ' '.join(name)
        if proceed(f'Are you sure you want to delete playlist "{name}"?'):
            pId = next((p['playlistId'] for p in playlists if p['title'] == name), None)
            if pId:
                ytmusic.delete_playlist(pId)
            else:
                print(f'Playlist "{name}" not found. Make sure it was typed correctly.')
                print('The playlists on YT Music are:')
                for pls in playlists:
                    print(f'{pls["title"]}')

# delete songs matching query or all songs from chosen collection
def deleteFrom(cName, collection, query):
    exact = False
    if not query:
        if proceed(f'This will delete ALL {cName} from YT Music (long process). Are you sure?'):
            for song in tqdm(collection):
                makeCall(cName, song, True)
                sleep(YTDelay)
    else:
        if '-e' in query:
            exact = True
            query.remove('-e')
        results = performQuery(config, query, collection, exact)
        if not results:
            return
        printSongs(f'\n\tFound {len(results)} songs from {cName}:', results)
        if proceed('Are you sure you want to delete these songs?'):
            for song in tqdm(results):
                makeCall(cName, song, True)
                sleep(YTDelay)

# call the right ytmusic function for the given collection
def makeCall(name, song, remove):
    if remove:
        switcher = {
            'uploads': lambda: ytmusic.delete_upload_entity(song['entityId']),
            'library': lambda: ytmusic.edit_song_library_status(song['feedbackTokens']['remove']),
            'likes': lambda: ytmusic.rate_song(song['videoId'], 'INDIFFERENT'),
        }
    else:
        switcher = {
            'uploads': lambda: ytmusic.upload_song(song),
            'library': lambda: ytmusic.edit_song_library_status(song['feedbackTokens']['add']),
            'likes': lambda: ytmusic.rate_song(song['videoId'], 'LIKE'),
        }

    func = switcher.get(name, lambda: print('Invalid command.'))
    return func()

# function to query all collections or delete all collections
def deleteAll(query):
    # user forgot query
    if query == '***':
        print('missing query')
        return
    for name, collection in [('uploads', uploads), ('library', library), ('likes', likes['tracks'])]:
        deleteFrom(name, collection, query)
    # user chose all, so nuke everything
    if not query:
        deletePlaylist(None)

# choose which function to call based on user command
def deleteOptions(command, query):
    switcher = {
        'all': lambda: deleteAll(None),
        'uploads': lambda: deleteFrom('uploads', uploads, None),
        'library': lambda: deleteFrom('library', library, None),
        'likes': lambda: deleteFrom('likes', likes['tracks'], None),
        'playlist': lambda: deletePlaylist(query),
        'query': lambda: deleteAll(query)
    }

    func = switcher.get(command, lambda: print('Invalid command.'))
    return func()

def commandOptions(command, query):
    switcher = {
        '-d': lambda: loadDir(query[0]),
        '-p': lambda: loadPlaylist(query[0]),
        'likes': lambda: addLikes(),
        'smart': lambda: smartPlaylists(),
        'delete': lambda: deleteThis(query),
        'config': lambda: configOptions(query),
        'resetAuth': lambda: authenticate(True)
    }

    func = switcher.get(command, lambda: printHelp())
    return func()

def configOptions(query):
    command = query[0] if query else ''
    switcher = {
        'reset': lambda: os.remove(configPath),
        'edit': lambda: editConfig(configPath),
    }

    func = switcher.get(command, lambda: print('Invalid config subcommand. Use either reset or edit.'))
    return func()

# print full formatted help
def printHelp():
    print(*commandHelp, sep='\n')
    for line in deleteHelp:
        print(f'\t{line}')

# user passed a directory so process all the music files in it
def loadDir(query):
    if os.path.isdir(query):
        for dirName, subdirList, fileList in os.walk(query):
            for filename in fileList:
                processFile(os.path.join(dirName,filename))
    else:
        print(f'Invalid directory: {query}')

# process playlist file
def loadPlaylist(query):
    if os.path.isfile(query):
        with openFile(query, 'r') as (playlist, err):
            if err:
                print(f'Problem opening playlist file: {err}')
                return
            lines = playlist.readlines()
            plistName = os.path.splitext(os.path.basename(playlist.name))[0]

            # see if playlist already exists and create one if not
            pName = next((p for p in playlists if p['title'] == plistName), None)
            pListID = ytmusic.create_playlist(plistName, '') if not pName else pName['playlistId']
            tempPlist = ytmusic.get_playlist(pListID, 10000)
            existing = set([t['videoId'] for t in tempPlist['tracks']])

            for line in lines:
                # skip comment lines in the playlist file
                if line.startswith('#'):
                    continue
                videoId = processFile(line.strip())
                if videoId:
                    playlistItems.add(videoId)

            # remove duplicates
            playlistItems -= existing
            # add all items to playlist at once
            ytmusic.add_playlist_items(pListID,playlistItems,None,True)
    else:
        print(f'{query} is not a valid file.')

# add all liked songs to library
def addLikes():
    for song in likes['tracks']:
        # search library for track and skip if it is already there
        if next((s for s in library if s['videoId'] == song['videoId']), None):
            print(f'SKIPPING "{song["title"]}" by {song["artists"][0]["name"]}: {song["duration"]}')
            continue
        # make sure the song can be added to the library
        if 'feedbackTokens' in song.keys():
            print(f'Adding song "{song["title"]}" by {song["artists"][0]["name"]}: {song["duration"]}')
            makeCall('library', song, False)
        # assume the song is a video
        else:
            print(f'"{song["title"]}" by {song["artists"][0]["name"]}: {song["duration"]} is a video')

# create or update the smart playlists from the config file
def smartPlaylists():
    global config
    MBdata = fillMBdata(cacheFile, config, MBfile, [('uploads', uploads), ('library', library), ('likes', likes['tracks'])])
    addTracks = {}
    libraryPlists = config.sections() or []
    rules = {}
    smartPlaylists = []

    if not MBdata or not libraryPlists:
        print('No smart playlists found in config')
        exit(0)
    for pName in libraryPlists:
        # check if a playlist with pName already exists
        plist = next((p for p in playlists if p['title'] == pName), None)
        # create playlist if necessary
        pListID = plist['playlistId'] if plist else ytmusic.create_playlist(pName, '')
        # grab the playlist and its list of tracks
        print(f'Downloading track list for playlist "{pName}"')
        smartPlaylists.append(ytmusic.get_playlist(pListID, 10000))
        rules[pName] = getRule(config[pName])
        addTracks[pListID] = []
    for song in tqdm(MBdata):
        for smart in smartPlaylists:
            # skip tracks already in playlist
            if next((s for s in smart['tracks'] if s['videoId'] == song['videoId']), None):
                continue
            if 'year' in rules[smart['title']].keys() and 'year' in song.keys() and song['year'] and int(song['year']) in rules[smart['title']]['year']:
                if 'genre' in rules[smart['title']].keys() and 'genres' in song.keys() and song['genres']:
                    if common_member(song['genres'], rules[smart['title']]['genre']):
                        if common_member(rules[smart['title']]['notGenre'], song['genres']):
                            continue
                        # track matches all rules so add it to playlist
                        addTracks[smart['id']].append(song['videoId'])
                        # we are done processing this playlist for this track
                        continue
                else:
                    if common_member(rules[smart['title']]['notGenre'], song['genres']):
                        continue
                    # track matches all rules present (no genre rules)
                    addTracks[smart['id']].append(song['videoId'])
                    continue
            if 'genre' in rules[smart['title']].keys() and 'genres' in song.keys() and song['genres']:
                if common_member(song['genres'], rules[smart['title']]['genre']):
                    if common_member(rules[smart['title']]['notGenre'], song['genres']):
                        continue
                    if 'year' in rules[smart['title']].keys() and 'year' in song.keys() and song['year']:
                        if int(song['year']) in rules[smart['title']]['year']:
                            addTracks[smart['id']].append(song['videoId'])
                            continue
                    else:
                        addTracks[smart['id']].append(song['videoId'])
    # add collected sonngs
    for id, tracks in addTracks.items():
        if tracks:
            name = next(p['title'] for p in smartPlaylists if p['id'] == id)
            print(f'Adding {len(tracks)} songs to playlist "{name}"')
            ytmusic.add_playlist_items(id,tracks,None,True)

# delete items from YT Music
def deleteThis(query):
    # no subcommand, print help
    if not query:
        print('Nothing to delete. Please specify what to delete')
        print(*deleteHelp, sep='\n')
        exit(0)
    # differentiate between None for deleting everything and user forgetting the query
    deleteCommand = query[0]
    if deleteCommand == 'playlist':
        query = query[1:] if len(query) > 1 else None
    else:
        query = query[1:] if len(query) > 1 else '***'
    deleteOptions(deleteCommand, query)


loadConfig()
authenticate()
sys.excepthook = myExceptHandler
# setMB(config, appVer)
uploads, library, playlists, likes = loadCache(ytmusic, cacheFile)
commandOptions(firstArg, sys.argv[2:] or None)

# make a csv file containing songs that could not be found on YT music
if notFound:
    fieldNames = notFound[0].keys() # ['Title','Artist','Duration','Filename']

    with openFile('missing.csv', 'w') as (csvFile, err):
        if err:
            print(f'Problem opening csv file: {err}')
        else:
            missing = csv.DictWriter(csvFile, fieldnames=fieldNames)
            missing.writeheader()

            for song in notFound:
                missing.writerow(song)

saveCache(cacheFile, MBfile, MBdata, [uploads, library, playlists, likes])
# print a bell character to the terminal to let the user know the process is complete
print('\a')
