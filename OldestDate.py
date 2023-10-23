# Borrowed and chopped from a great project at https://github.com/kernitus/beets-oldestdate

import datetime
from dateutil import parser

import musicbrainzngs

# def setMB(config, appVer):
#     musicbrainzngs.set_hostname(config['DEFAULT']['mbhost'])
#     musicbrainzngs.set_rate_limit(1, config['DEFAULT'].getfloat('mbrateLimit'))
#     musicbrainzngs.set_useragent(
#         'Youtube Music Sync',
#         appVer,
#         ''
#     )


# Extract first valid work_id from recording
def _get_work_id_from_recording(recording):
    work_id = None

    if 'work-relation-list' in recording:
        for work_rel in recording['work-relation-list']:
            if 'work' in work_rel:
                current_work = work_rel['work']
                if 'id' in current_work:
                    work_id = current_work['id']
                    break

    return work_id


# Returns whether this recording contains at least one of the specified artists
def _contains_artist(recording, artist_ids):
    artist_found = False
    if 'artist-credit' in recording:
        for artist in recording['artist-credit']:
            if 'artist' in artist:
                artist = artist['artist']
                if 'id' in artist and artist['id'] in artist_ids:  # Contains at least one of the identified artists
                    artist_found = True
                    break
    return artist_found


# Extract artist ids from a recording
def _get_artist_ids_from_recording(recording):
    ids = []

    if 'artist-credit' in recording:
        for artist in recording['artist-credit']:
            if 'artist' in artist:
                artist = artist['artist']
                if 'id' in artist:
                    ids.append(artist['id'])
    return ids


# Returns whether given fetched recording is a cover of a work
def _is_cover(recording):
    if 'work-relation-list' in recording:
        for work in recording['work-relation-list']:
            if 'attribute-list' in work:
                if 'cover' in work['attribute-list']:
                    return True
    return False


class DateWrapper(datetime.datetime):
    """
    Wrapper class for datetime objects.
    Allows comparison between dates taking into
    account the month and day being optional.
    """

    def __new__(cls, y: int = None, m: int = None, d: int = None, iso_string: str = None):
        """
        Create a new datetime object using a convenience wrapper.
        Must specify at least one of either year or iso_string.
        :param y: The year, as an integer
        :param m: The month, as an integer (optional)
        :param d: The day, as an integer (optional)
        :param iso_string: A string representing the date in the format YYYYMMDD. Month and day are optional.
        """
        if y is not None:
            year = min(max(y, datetime.MINYEAR), datetime.MAXYEAR)
            month = m if (m is not None and 0 < m <= 12) else 1
            day = d if (d is not None and 0 < d <= 31) else 1
        elif iso_string is not None:
            iso_string = iso_string.replace("??", "01")
            parsed = parser.isoparse(iso_string)
            return datetime.datetime.__new__(cls, parsed.year, parsed.month, parsed.day)
        else:
            raise TypeError("Must specify a value for year or a date string")

        return datetime.datetime.__new__(cls, year, month, day)

    @classmethod
    def today(cls):
        today = datetime.date.today()
        return DateWrapper(today.year, today.month, today.day)

    def __init__(self, y=None, m=None, d=None, iso_string=None):
        if y is not None:
            self.y = min(max(y, datetime.MINYEAR), datetime.MAXYEAR)
            self.m = m if (m is None or 0 < m <= 12) else 1
            self.d = d if (d is None or 0 < d <= 31) else 1
        elif iso_string is not None:
            # Remove any hyphen separators
            iso_string = iso_string.replace("??", "01")
            iso_string = iso_string.replace("-", "")
            length = len(iso_string)

            if length < 4:
                raise ValueError("Invalid value for year")

            self.y = int(iso_string[:4])
            self.m = None
            self.d = None

            # Month and day are optional
            if length >= 6:
                self.m = int(iso_string[4:6])
                if length >= 8:
                    self.d = int(iso_string[6:8])
        else:
            raise TypeError("Must specify a value for year or a date string")

    def __lt__(self, other):
        if self.y != other.y:
            return self.y < other.y
        elif self.m is None:
            return False
        else:
            if other.m is None:
                return True
            elif self.m == other.m:
                if self.d is None:
                    return False
                else:
                    if other.d is None:
                        return True
                    else:
                        return self.d < other.d
            else:
                return self.m < other.m

    def __eq__(self, other):
        if self.y != other.y:
            return False
        elif self.m is not None and other.m is not None:
            if self.d is not None and other.d is not None:
                return self.d == other.d
            else:
                return self.m == other.m
        else:
            return self.m == other.m

_recordings_cache = dict()
# Fetch work, including recording relations
def _fetch_work(work_id):
    return musicbrainzngs.get_work_by_id(work_id, ['recording-rels'])['work']



# Return whether the recording has a work id
def _has_work_id(recording_id):
    recording = _get_recording(recording_id)
    work_id = _get_work_id_from_recording(recording)
    return work_id is not None


# Fetch and cache recording from MusicBrainz, including releases and work relations
def _fetch_recording(recording_id):
    recording = musicbrainzngs.get_recording_by_id(recording_id, ['artists', 'releases', 'work-rels'])['recording']
    _recordings_cache[recording_id] = recording
    return recording

# Get recording from cache or MusicBrainz
def _get_recording(recording_id):
    return _recordings_cache[
        recording_id] if recording_id in _recordings_cache else _fetch_recording(recording_id)

# Get oldest date from a recording
def _extract_oldest_recording_date(recordings, starting_date, is_cover, approach):
    oldest_date = starting_date

    for rec in recordings:
        if 'recording' not in rec:
            continue
        rec_id = rec['recording']
        if 'id' not in rec_id:
            continue
        rec_id = rec_id['id']

        # If a cover, filter recordings to only keep covers. Otherwise, remove covers
        if is_cover != ('attribute-list' in rec and 'cover' in rec['attribute-list']):
            # We can't filter by author here without fetching each individual recording.
            _recordings_cache.pop(rec_id, None)  # Remove recording from cache
            continue

        if 'begin' in rec:
            date = rec['begin']
            if date:
                try:
                    date = DateWrapper(iso_string=date)
                    if date < oldest_date:
                        oldest_date = date
                except ValueError:
                    print(f"Could not parse date {date} for recording {rec}")

        # Remove recording from cache if no longer needed
        if approach == 'recordings' or (approach == 'hybrid' and oldest_date != starting_date):
            _recordings_cache.pop(rec_id, None)

    return oldest_date

# Get oldest date from a release
def _extract_oldest_release_date(recordings, starting_date, is_cover, artist_ids, release_types = None):
    oldest_date = starting_date

    for rec in recordings:
        rec_id = rec['recording'] if 'recording' in rec else rec
        if 'id' not in rec_id:
            continue
        rec_id = rec_id['id']

        fetched_recording = None

        # Shorten recordings list, but if song is a cover, only keep covers
        if is_cover:
            if 'attribute-list' not in rec or 'cover' not in rec['attribute-list']:
                _recordings_cache.pop(rec_id, None)  # Remove recording from cache
                continue
            else:
                # Filter by artist, but only if cover (to avoid not matching solo careers of former groups)
                fetched_recording = _get_recording(rec_id)
                if not _contains_artist(fetched_recording, artist_ids):
                    _recordings_cache.pop(rec_id, None)  # Remove recording from cache
                    continue
        elif 'attribute-list' in rec and 'cover' in rec['attribute-list']:
            _recordings_cache.pop(rec_id, None)  # Remove recording from cache
            continue

        if not fetched_recording:
            fetched_recording = _get_recording(rec_id)

        if 'release-list' in fetched_recording:
            for release in fetched_recording['release-list']:
                if release_types is None or (  # Filter by recording type, i.e. Official
                        'status' in release and release['status'] in release_types):
                    if 'date' in release:
                        release_date = release['date']
                        if release_date:
                            try:
                                date = DateWrapper(iso_string=release_date)
                                if date < oldest_date:
                                    oldest_date = date
                            except ValueError:
                                print(f"Could not parse date {release_date} for recording {rec}")

        _recordings_cache.pop(rec_id, None)  # Remove recording from cache

    return oldest_date

# Iterates through a list of recordings and returns oldest date
def _iterate_dates(recordings, starting_date, is_cover, artist_ids, approach = 'releases'):
    oldest_date = starting_date

    # Look for oldest recording date
    if approach in ('recordings', 'hybrid', 'both'):
        oldest_date = _extract_oldest_recording_date(recordings, starting_date, is_cover, approach)

    # Look for oldest release date for each recording
    if approach in ('releases', 'both') or (approach == 'hybrid' and oldest_date == starting_date):
        oldest_date = _extract_oldest_release_date(recordings, oldest_date, is_cover, artist_ids)

    return None if oldest_date == DateWrapper.today() else oldest_date

def _get_oldest_date(recording_id, item_date):
    recording = _get_recording(recording_id)
    is_cover = _is_cover(recording)
    work_id = _get_work_id_from_recording(recording)
    artist_ids = _get_artist_ids_from_recording(recording)

    today = DateWrapper.today()

    # If no work id, check this recording against embedded date
    starting_date = item_date if item_date is not None and not work_id else today

    if not work_id:  # Only look through this recording
        return _iterate_dates([recording], starting_date, is_cover, artist_ids)

    # Fetch work, including associated recordings
    work = _fetch_work(work_id)

    if 'recording-relation-list' not in work:
        print(f'Work {work_id} has no valid associated recordings! Please choose another recording or amend the data!')
        return None

    return _iterate_dates(work['recording-relation-list'], starting_date, is_cover, artist_ids)
