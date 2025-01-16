from flask import Flask, render_template, request
import subprocess
import sys
import json

app = Flask(__name__)

def get_playlist_info(playlist_link):
    """
    Extracts titles and thumbnails from the playlist using youtube-dl.

    Args:
        playlist_link: The URL of the playlist.

    Returns:
        A list of dictionaries, where each dictionary contains the 'title' and 'thumbnail' 
        for a track, or None on failure.
    """
    try:
        command = [
            sys.executable,
            "-m",
            "youtube_dl",
            "-e", #get title
            "--get-title", #get title
            "--get-thumbnail", #get thumbail
            "-s",
            "--no-warnings",
            playlist_link
        ]
        process = subprocess.run(command, capture_output=True, text=True, check=True)
        print("info gathered")
        output = process.stdout
        lines = output.strip().split('\n')
        
        items = []
        for i in range(0,len(lines),2):
          try:
            items.append(
                {
                    'title': lines[i].strip(),
                    'thumbnail': lines[i+1].strip()
                  }
            )
            # print({
            #         'title': lines[i+1].strip(),
            #         'thumbnail': lines[i].strip()
            #       })
          except IndexError:
             print("IndexError, unable to get track")
             continue

        return items
    except subprocess.CalledProcessError as e:
        print(f"Error running youtube-dl: {e}")
        print(f"youtube-dl stderr: {e.stderr}")
        return None
    except FileNotFoundError:
        print("Error: youtube-dl not found. Please make sure it's installed.")
        return None

@app.route('/', methods=['GET', 'POST'])
def index():
    playlist_data = None
    error_message = None
    if request.method == 'POST':
        playlist_url = request.form['playlist_url']
        playlist_data = get_playlist_info(playlist_url)
        if playlist_data:
            playlist_data_with_index = []
            for i, track in enumerate(playlist_data):
                playlist_data_with_index.append({
                    'index': i,
                    'title': track['title'],
                    'thumbnail': track['thumbnail']
                })
            playlist_data = playlist_data_with_index
        if playlist_data is None:
            error_message = "Error loading playlist. Please check the URL."
    return render_template('index.html', playlist_data=playlist_data, error_message=error_message)

if __name__ == '__main__':
    app.run(debug=True)