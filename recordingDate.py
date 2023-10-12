"""
Most of this code borrowed from Tod Weitzel. License and copyright below.

MIT License

Copyright (c) 2016 Tod Weitzel https://github.com/tweitzel

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import musicbrainzngs

relations = ['edit', 'first track release', 'remaster']

def make_date_values(date_str):
    date_parts = date_str.split('-')
    date_values = {}
    for key in ('year', 'month', 'day'):
        if date_parts:
            date_part = date_parts.pop(0)
            try:
                date_num = int(date_part)
            except ValueError:
                continue
            date_values[key] = date_num
    return date_values

def recurse_relations(mb_track_id, oldest_release, relation_type):
    x = musicbrainzngs.get_recording_by_id(
        mb_track_id,
        includes=['releases', 'recording-rels'])

    if 'recording-relation-list' in x['recording'].keys():
        # recurse down into edits and remasters.
        # Note remasters are deprecated in musicbrainz, but some entries
        # may still exist.
        for subrecording in x['recording']['recording-relation-list']:
            if ('direction' in subrecording.keys() and
                    subrecording['direction'] == 'backward'):
                continue
            # skip new relationship category samples
            if subrecording['type'] not in relations:
                continue
            if 'artist' in x['recording'].keys() and x['recording']['artist'] != subrecording['artist']:
                print(f'Skipping relation with arist {subrecording["artist"]} that does not match {x["recording"]["artist"]}')
                continue
            (oldest_release, relation_type) = recurse_relations(
                subrecording['target'],
                oldest_release,
                subrecording['type'])
    for release in x['recording']['release-list']:
        if 'date' not in release.keys():
            # A release without a date. Skip over it.
            continue
        release_date = make_date_values(release['date'])
        if 'year' not in release_date.keys():
            continue
        if (oldest_release['year'] is None or
                oldest_release['year'] > release_date['year']):
            oldest_release = release_date
        elif oldest_release['year'] == release_date['year']:
            if ('month' in release_date.keys() and
                    'month' in oldest_release.keys() and
                    oldest_release['month'] > release_date['month']):
                oldest_release = release_date
    return (oldest_release, relation_type)
