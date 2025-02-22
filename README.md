# Local-Music-Hub
Local Music Hub is an all-in-one music streaming solution that aggregates content from YouTube and Spotify. It enables users to search for songs, download audio tracks, manage playlists, and enjoy seamless playback—all powered by VLC and an intuitive web interface.

Features

YouTube Search & Download:
Search for music videos using the YouTube Data API and download the best audio track with yt_dlp, converting it to MP3 via FFmpeg.
Spotify Playlist Import:
Import playlists directly from Spotify. The app retrieves track details using Spotipy, finds the corresponding YouTube videos, and downloads the audio.
Playlist & Queue Management:
Create and manage playlists, reorder the in-memory song queue, and automatically play through queued tracks.
Playback Controls:
Enjoy features like play, pause, stop, skip, rewind, and restart through VLC-powered playback.
Database Integration:
Uses SQLAlchemy with SQLite to store song metadata and playlist details, ensuring a persistent and organized music library.
Installation

Prerequisites
Python 3.6+
FFmpeg: Ensure FFmpeg is installed and its path is correctly set in the code.
VLC: Install VLC media player for audio playback.
API Keys/Credentials:
YouTube Data API key
Spotify API credentials


Usage
Home Page:
View your song queue and all playlists. Use the search functionality to find new music on YouTube.
Search:
Enter a query to search for videos. Select a song to add it to your queue or directly play it.
Playback Controls:
Use the provided buttons to play, pause, stop, skip, or rewind tracks. The in-memory queue automatically advances when a song finishes.
Playlist Management:
Create new playlists, add or remove songs, and reorder the queue with intuitive controls.
Spotify Integration:
Import a Spotify playlist by providing its URL. The app will retrieve the playlist details, download the corresponding songs from YouTube, and add them to your library.
