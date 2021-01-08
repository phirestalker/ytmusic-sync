# YT Music Sync

Scan your music files and add them to YT Music using information from their tags.
Song will first be found on YT Music and if they are not found you can set them to be uploaded.
Create smart playlists on YT Music using simple rules for year and genre, and keep them updated.
Delete all of your likes, uploads, and/or library. Also delete items matching a query.

## Setup

After cloning this repository, you will need to copy request headers from your browser.
This program uses a great project named ytmusicapi to interact with YT Music. I will link to their setup instructions as they are relevant here: https://ytmusicapi.readthedocs.io/en/latest/setup.html#authenticated-requests

## Usage

Available commands are:
-d directory	Scans all subdirectories under directory for music files and adds them to library
-p playlist	Adds all playlist items to library and to the named playlist
likes	Adds all liked songs to your library
smart	Creates and updates playlists by rules set in config file
config	perform config file operations
	Subcommands:
	edit	Opens the config file for editing in your default editor
	reset	Resets the config file to default settings
resetAuth	Use to delete auth file and paste new credentials
delete		Deletes specified items
	Available delete subcommands are:

	all		deletes everything from YT music!!
	uploads		deletes all uploaded music
	library		deletes all songs from your library
	likes		remove all songs from your likes
	playlist	removes all playlists or specified playlist by name
	query		delete items that match a query from uploads, library, and likes
				-e option will perform and exact search instead of a fuzzy search
				A string of words will match ALL words
				artist:query will only search artist for "query"
				title:query will only search song title for "query"
				album:query will only search album for "query"

Note: if you use field search terms, all query terms must be contained in them. For example:
	Correct:	artist:queen "album:news of the world"
	Correct:	"title:pumped up kicks"
	Incorrect:	"artist:black eyed peas" retarded
