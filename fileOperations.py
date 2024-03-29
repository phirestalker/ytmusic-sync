import os, subprocess, platform
from ytmusicapi import YTMusic
import pathlib
import pickle
import csv
from tqdm import tqdm


from utils import *

def editConfig(configPath):
    if platform.system() == 'Darwin':       # macOS
        subprocess.call(('open', configPath))
    elif platform.system() == 'Windows':    # Windows
        os.startfile(configPath)
    else:                                   # linux variants
        subprocess.call(('xdg-open', configPath))

# save the cachefile if there were no changes made
def saveCache(cacheFile, MBfile, MBdata, cache):
    if MBdata:
        with openFile(MBfile,'wb') as (f, err):
            if err:
                print(f'Problem writing MB cache file: {err}')
            else:
                pickle.dump(MBdata, f)
    if cache:
        with openFile(cacheFile,'wb') as (f, err):
            if err:
                print(f'Problem writing cache file: {err}')
            else:
                pickle.dump(cache, f)
                print('saved cache file')
    # with openFile('library.csv','w') as (f, err):
    #     missing = csv.DictWriter(f, fieldnames=cache[1][0].keys())
    #     missing.writeheader()
    #
    #     for song in cache[1]:
    #         missing.writerow(song)

# load the cachefile if it exists and then check to make sure cache is not outdated
# otherwise just load the library, uploads, playlists, and liked songs from YT music
def loadCache(ytmusic, cacheFile):
    uploads = None
    library = None
    playlists = None
    likes = None
    if cacheFile.exists():
        print('Loading uploads and library from cache file')
        with openFile(cacheFile, 'rb') as (f, err):
            if err:
                print(f'Problem loading cache: {err}')
            else:
                uploads, library, playlists, likes = pickle.load(f)
    try:
        check = ytmusic.get_library_upload_songs(1, 'recently_added')
        if not uploads or check[0]['videoId'] != uploads[0]['videoId']:
            print('getting uploaded songs from YT music')
            uploads = ytmusic.get_library_upload_songs(100000, 'recently_added')
        check = ytmusic.get_library_songs(1, True, 'recently_added')
        if not library or check[0]['videoId'] != library[0]['videoId']:
            print('getting library songs from YT music')
            library = ytmusic.get_library_songs(100000, True, 'recently_added')
        print('getting library playlists from YT music')
        playlists = ytmusic.get_library_playlists(500)
        check = ytmusic.get_liked_songs(1)
        if not likes or check['trackCount'] != likes['trackCount']:
            print('getting liked songs from YT music')
            likes = ytmusic.get_liked_songs(100000)
    except Exception:
        os.remove(authFile)
        print('Authorization expired. Next run will require pasted headers.')
        exit(1)
    saveCache(cacheFile, None, None, [uploads, library, playlists, likes])
    return uploads, library, playlists, likes

def fillMBdata(cacheFile, config, MBfile, collections):

    MBdata = None
    if MBfile.exists():
        with openFile(MBfile,'rb') as (f, err):
            if err:
                print(f'Problem loading data from MB cache file: {err}')
            else:
                MBdata = pickle.load(f)
                MBdata = convertMBdata(MBdata)
                print(f'Loaded {len(MBdata)} entries from MusicBrainz cache file')
    for name, songList in collections:
        # uploads has a different tag for artist
        artist = 'artist' if 'artist' in songList[0].keys() else 'artists'
        print(f' Getting MB data for songs in {name}')
        for song in tqdm(songList):
            # skip songs already pulled from MusicBrainz
            if song['videoId'] in MBdata:
                continue
            # if 'duration' in song:
            #     t = datetime.strptime(song['duration'], '%M:%S')
            #     durationDelta = timedelta(minutes=t.minute, seconds=t.second)
            #     duration = int(durationDelta.total_seconds() * 1000)
            # else:
            #     duration = 0
            songInfo = getMBinfo(config, song['title'], song[artist][0]['name'])
            if songInfo:
                MBdata[song['videoId']] = songInfo
        saveCache(cacheFile, MBfile, MBdata, None)
    return MBdata

def convertMBdata(MBdata):
    if isinstance(MBdata, list):
        converted = {}
        for s in MBdata:
            converted[s['videoId']] = {'duration': s['duration'], 'year': s['year'], 'genres': s['genres'], 'mbID': s['mbID']}
        return converted
    else:
        return MBdata
