import os
import threading
import time
from collections import deque
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from googleapiclient.discovery import build
import vlc
import yt_dlp as youtube_dl
from flask_executor import Executor
from random import shuffle
from markupsafe import Markup


import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from googleapiclient.discovery import build


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///songs.db'
app.config['EXECUTOR_TYPE'] = 'thread'
app.config['EXECUTOR_MAX_WORKERS'] = 1
db = SQLAlchemy(app)
executor = Executor(app)

playlists_songs = db.Table('playlists_songs',
                           db.Column('song_id', db.String, db.ForeignKey('song.id')),
                           db.Column('playlist_id', db.Integer, db.ForeignKey('playlist.id')))

class Playlist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String)
    songs = db.relationship('Song', secondary=playlists_songs, backref=db.backref('playlists', lazy=True))

class Song(db.Model):
    id = db.Column(db.String, primary_key=True)
    title = db.Column(db.String)
    thumbnail_url = db.Column(db.String)
    url = db.Column(db.String)
    file_path = db.Column(db.String)

player = None
now_playing = None
song_queue = deque()  # This is our in-memory queue

@app.route('/')
def index():
    # Query the database for the songs in the queue
    songs_in_queue = [Song.query.get(song_id) for song_id in song_queue]
    playlists = Playlist.query.all()
    return render_template('index.html', songs=songs_in_queue, playlists=playlists)



@app.route('/playlist/<int:playlist_id>')
def playlist(playlist_id):
    playlist = Playlist.query.get(playlist_id)
    return render_template('playlist.html', playlist=playlist)

@app.route('/search', methods=['POST'])
def search():
    search_request = request.form.get('query')
    youtube = build('youtube', 'v3', developerKey='')
    youtube_request = youtube.search().list(part='snippet', maxResults=5, q=search_request, type='video')
    response = youtube_request.execute()

    results = []
    for item in response['items']:
        results.append({
            'title': Markup(item['snippet']['title']),
            'thumbnail': item['snippet']['thumbnails']['default']['url'],
            'id': item['id']['videoId']
            })

    return render_template('search.html', results=results)

@app.route('/add', methods=['POST'])
def add_to_queue():
    id = request.form.get('id')
    title = request.form.get('title')
    thumbnail = request.form.get('thumbnail')
    url = f"https://www.youtube.com/watch?v={id}"

    # Check if the song is already downloaded
    song = Song.query.filter_by(id=id).first()
    if song is None:
        # Download the song
        file_path = download_song(url)

        # Add the song to the database
        song = Song(id=id, title=title, thumbnail_url=thumbnail, url=url, file_path=file_path)
        db.session.add(song)
        db.session.commit()

    # Add the song to the "All Songs" playlist
    all_songs_playlist = Playlist.query.filter_by(name='All Songs').first()
    all_songs_playlist.songs.append(song)
    db.session.commit()

    # Add song to the in-memory queue
    song_queue.append(song.id)
    return redirect(url_for('index'))

@app.route('/play', methods=['POST'])
def play():
    global now_playing
    song_id = request.form.get('id')
    song = Song.query.filter_by(id=song_id).first()
    if song and song.title != now_playing:
        if song.file_path is None:  # If the song hasn't been downloaded yet
            song.file_path = download_song(song.url)
            db.session.commit()
        play_song(song.file_path)
        now_playing = song.title
    return redirect('/')

def download_song(url):

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': 'songs/%(id)s.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'ffmpeg_location': 'C:\\\\FFmpeg\\\\bin\\\\ffmpeg.exe',  # ensure the path to ffmpeg is correct
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        }
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            file_path = ydl.prepare_filename(info_dict)
            ydl.download([url])
            # change the extension to .mp3
            file_path = os.path.splitext(file_path)[0] + '.mp3'
            return file_path

@app.route('/pause', methods=['POST'])
def pause():
    global player
    if player is not None:
        player.pause()  # This will pause the player if it's playing, or unpause it if it's paused
    return redirect('/')

@app.route('/stop', methods=['POST'])
def stop():
    global player
    if player is not None:
        player.stop()
    return redirect('/')

@app.route('/skip', methods=['POST'])
def skip():
    global player
    if player is not None:
        player.stop()
    return redirect('/')

@app.route('/rewind', methods=['POST'])
def rewind():
    global player
    if player is not None:
        player.set_time(player.get_time() - 10000)  # Rewind 10 seconds
    return redirect('/')

@app.route('/start', methods=['POST'])
def start():
    global player
    if player is not None:
        player.set_time(0)  # Go to the start of the song
    return redirect('/')

@app.route('/play_current_queue', methods=['POST'])
def play_current_queue():
    global song_queue, player, queue_thread
    if player is not None:
        player.stop()  # Stop the current song
    if song_queue:
        # Start the first song
        song_id = song_queue.popleft()
        song = Song.query.get(song_id)
        play_song(song.file_path)
        # Start the queue monitoring thread
        queue_thread = threading.Thread(target=start_playing_queue)
        queue_thread.start()
    return redirect('/')

@app.route('/move_up', methods=['POST'])
def move_up():
    song_id = request.form.get('id')
    try:
        index = song_queue.index(song_id)
        if index != 0:  # If it's not the first item
            song_queue[index], song_queue[index - 1] = song_queue[index - 1], song_queue[index]  # Swap with the previous item
    except ValueError:
        pass  # The song is not in the queue
    return redirect(url_for('index'))

@app.route('/move_down', methods=['POST'])
def move_down():
    song_id = request.form.get('id')
    try:
        index = song_queue.index(song_id)
        if index != len(song_queue) - 1:  # If it's not the last item
            song_queue[index], song_queue[index + 1] = song_queue[index + 1], song_queue[index]  # Swap with the next item
    except ValueError:
        pass  # The song is not in the queue
    return redirect(url_for('index'))

@app.route('/add_playlist_to_queue', methods=['POST'])
def add_playlist_to_queue():
    playlist_id = request.form.get('playlist_id')
    playlist = Playlist.query.get(playlist_id)
    for song in playlist.songs:
        song_queue.append(song.id)
    return redirect(url_for('index'))  # Redirect to the index page

@app.route('/shuffle_queue', methods=['POST'])
def shuffle_queue():
    shuffle(song_queue)
    return redirect('/')

@app.route('/remove_from_queue', methods=['POST'])
def remove_from_queue():
    song_id = request.form.get('id')
    while song_id in song_queue:
        song_queue.remove(song_id)
    return redirect(url_for('index'))

@app.route('/create_playlist', methods=['POST'])
def create_playlist():
    name = request.form.get('name')
    new_playlist = Playlist(name=name)
    db.session.add(new_playlist)
    db.session.commit()
    return redirect('/')

@app.route('/add_to_playlist', methods=['POST'])
def add_to_playlist():
    song_id = request.form.get('id')
    title = request.form.get('title')
    thumbnail = request.form.get('thumbnail')
    url = f"https://www.youtube.com/watch?v={song_id}"

    # Check if the song is already downloaded
    song = Song.query.filter_by(id=song_id).first()
    if song is None:
        # Download the song
        file_path = download_song(url)

        # Add the song to the database
        song = Song(id=song_id, title=title, thumbnail_url=thumbnail, url=url, file_path=file_path)
        db.session.add(song)
        db.session.commit()

    # Get a list of all playlists except "All Songs"
    playlists = Playlist.query.filter(Playlist.name != 'All Songs').all()

    return render_template('add_to_playlist.html', song_id=song_id, playlists=playlists)


@app.route('/add_song_to_playlist', methods=['POST'])
def add_song_to_playlist():
    song_id = request.form.get('song_id')
    playlist_id = request.form.get('playlist_id')

    song = Song.query.get(song_id)
    playlist = Playlist.query.get(playlist_id)

    playlist.songs.append(song)

    #if not in the all songs playlist, add it
    all_songs_playlist = Playlist.query.filter_by(name='All Songs').first()
    if song not in all_songs_playlist.songs:
        all_songs_playlist.songs.append(song)
        
    db.session.commit()

    return redirect(url_for('index'))

@app.route('/remove_from_playlist', methods=['POST'])
def remove_from_playlist():
    song_id = request.form.get('song_id')
    playlist_id = request.form.get('playlist_id')

    song = Song.query.get(song_id)
    playlist = Playlist.query.get(playlist_id)

    playlist.songs.remove(song)
    db.session.commit()

    return redirect(url_for('playlist', playlist_id=playlist_id))

@app.route('/delete_playlist', methods=['POST'])
def delete_playlist():
    playlist_id = request.form.get('playlist_id')
    playlist = Playlist.query.get(playlist_id)

    # Prevent deleting the "All Songs" playlist
    if playlist.name == 'All Songs':
        return redirect('/')  # Redirect to home page

    # Remove all songs from the playlist
    for song in playlist.songs:
        playlist.songs.remove(song)

    # Delete the playlist
    db.session.delete(playlist)
    db.session.commit()

    return redirect('/')

@app.route('/clear_queue', methods=['POST'])
def clear_queue():
    global song_queue
    song_queue = deque()
    return redirect('/')




def start_playing_queue():
    global song_queue
    while True:
        if not song_queue:  # If the queue is empty
            time.sleep(1)  # Wait for 1 second before checking again
            continue  # Skip the rest of this iteration and go back to the start of the loop
        state = player.get_state()
        if state == vlc.State.Ended or state == vlc.State.Stopped:
            if song_queue:
                song_id = song_queue.popleft()
                song = Song.query.get(song_id)
                play_song(song.file_path)
        time.sleep(1)  # Wait for 1 second before checking the player state again


def play_song(file):
    global player
    if player is not None:  # If there is a song currently playing
        player.stop()  # Stop the currently playing song
    player = vlc.MediaPlayer(file)  # Start a new song
    player.play()





"""
Spotify Integration
"""
spotify_credentials = {
    
}
youtube_credentials = {
    
}


def getTracks(playlistURL):
    client_credentials_manager = SpotifyClientCredentials(spotify_credentials["client_id"], spotify_credentials["client_secret"])
    spotify = spotipy.Spotify(client_credentials_manager=client_credentials_manager)
    
    # Get playlist details
    playlist_details = spotify.playlist(playlistURL)
    playlist_name = playlist_details['name']

    # Get tracks
    results = spotify.playlist_tracks(playlistURL)
    trackList = []
    for i in results["items"]:
        if len(i["track"]["artists"]) == 1:
            trackList.append(i["track"]["name"] + " - " + i["track"]["artists"][0]["name"])
        else:
            nameString = ""
            for index, b in enumerate(i["track"]["artists"]):
                nameString += b["name"]
                if len(i["track"]["artists"]) - 1 != index:
                    nameString += ", "
            trackList.append(i["track"]["name"] + " - " + nameString)
    return playlist_name, trackList



def searchYoutube(songName):
    youtube = build('youtube', 'v3', developerKey=youtube_credentials["api_key"])
    request = youtube.search().list(
        part="snippet",
        maxResults=1,
        q=songName,
        type="video",
    )
    response = request.execute()
    videoId = response['items'][0]['id']['videoId']
    return "https://www.youtube.com/watch?v=" + videoId


@app.route('/spotify')
def spotify():
    return render_template('spotify.html')

@app.route('/import_spotify_playlist', methods=['POST'])
def import_spotify_playlist():
    playlist_link = request.form.get('playlist_link')
    playlist_name, tracks = getTracks(playlist_link)
    playlist = Playlist.query.filter_by(name=playlist_name).first()
    if playlist is None:
        # If the playlist doesn't exist, create it
        playlist = Playlist(name=playlist_name)
        db.session.add(playlist)
    for track in tracks:
        youtube_link = searchYoutube(track)
        youtube_id = youtube_link.split("=")[-1]
        song = Song.query.filter_by(id=youtube_id).first()
        if song is None:
            file_path = download_song(youtube_link)
            if file_path is None:
                # If there was an error downloading the song, skip it
                continue

            # Add the song to the database
            song = Song(id=youtube_id, title=track, thumbnail_url=None, url=youtube_link, file_path=file_path)
            db.session.add(song)

        # Add the song to the "All Songs" playlist
        all_songs_playlist = Playlist.query.filter_by(name='All Songs').first()
        all_songs_playlist.songs.append(song)

        # Add the song to the new playlist
        playlist.songs.append(song)

        db.session.commit()

        # Commented out: do not add song to the in-memory queue
        # song_queue.append(song.id)
    return redirect('/')




if __name__ == "__main__":
    with app.app_context():
        if not os.path.exists('songs.db'):
            db.create_all()
    
        # Check if "All Songs" playlist exists, if not, create it
        all_songs_playlist = Playlist.query.filter_by(name='All Songs').first()
        if all_songs_playlist is None:
            all_songs_playlist = Playlist(name='All Songs')
            db.session.add(all_songs_playlist)
            db.session.commit()
    
    app.run(host='0.0.0.0', port=1234, debug=True)