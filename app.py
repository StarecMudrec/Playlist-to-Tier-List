from flask import Flask, render_template, request
from yandex_music import Client
import yt_dlp
import re
import logging
from urllib.parse import urlparse
import os
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

def _first_url_from_text(text: str) -> str | None:
    """
    If the user pastes an <iframe ...> snippet or any text that contains URLs,
    grab the first one.
    """
    m = re.search(r'https?://[^"\s<>]+', text)
    return m.group(0) if m else None


def _clean_url_for_matching(url: str) -> str:
    """
    Clean URL for regex matching where query params are usually irrelevant (e.g. Yandex links with utm_*).
    IMPORTANT: Do not use this for yt-dlp inputs, because many playlist URLs (e.g. YouTube) rely on query params.
    """
    parsed = urlparse(url)
    return parsed._replace(query="", fragment="").geturl()


def _clean_url_for_ydl(url: str) -> str:
    """Keep query params (needed for many playlist URLs), strip only fragments."""
    parsed = urlparse(url)
    return parsed._replace(fragment="").geturl()


def _is_spotify_url(url: str) -> bool:
    return bool(re.search(r'open\.spotify\.com/(playlist|album)/', url))


def _spotify_items_from_url(url: str):
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    if not client_id or not client_secret:
        logging.warning("Spotify credentials not set  -  skipping Spotify fetch")
        return None

    m = re.search(r'open\.spotify\.com/(playlist|album)/([A-Za-z0-9]+)', url)
    if not m:
        return None

    resource_type, resource_id = m.group(1), m.group(2)

    try:
        auth = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
        sp = spotipy.Spotify(auth_manager=auth)

        items = []
        if resource_type == "playlist":
            page = sp.playlist_tracks(resource_id)
        else:
            page = sp.album_tracks(resource_id)

        while page:
            for item in page.get("items", []):
                track = item.get("track") or item  # album_tracks returns tracks directly
                if not track or not track.get("name"):
                    continue
                title = track["name"]
                artists = ", ".join(a["name"] for a in track.get("artists", []))
                images = track.get("album", {}).get("images", []) or []
                thumb = images[0]["url"] if images else ""
                items.append({
                    "title": f"{title} - {artists}" if artists else title,
                    "thumbnail": thumb,
                    "id": track.get("id") or title,
                })
            page = sp.next(page) if page.get("next") else None

        return items if items else None

    except Exception as e:
        logging.error(f"Spotify fetch error: {e}")
        return None


def extract_yandex_playlist_info(user_input: str):
    """
    Extract (user_id, playlist_id) from Yandex Music formats:
    - https://music.yandex.ru/users/<user>/playlists/<id>
    - https://music.yandex.ru/iframe/playlist/<user>/<id>
    - <iframe ... src="...">...</iframe>  (we'll pull the URL out)

    Note: links like /playlists/lk.<uuid> don't contain the owner+numeric id; for those,
    ask the user to paste the iframe snippet (it includes /iframe/playlist/<user>/<id>).
    """
    raw = (user_input or "").strip()
    if not raw:
        return None, None

    url = raw if raw.startswith("http") else (_first_url_from_text(raw) or raw)
    url = _clean_url_for_matching(url)

    # /users/<user>/playlists/<id>
    m = re.search(r'music\.yandex\.(?:ru|com)/users/([^/]+)/playlists/([^/]+)$', url)
    if m:
        return m.group(1), m.group(2)

    # /iframe/playlist/<user>/<id>
    m = re.search(r'music\.yandex\.(?:ru|com)/iframe/playlist/([^/]+)/([^/]+)$', url)
    if m:
        return m.group(1), m.group(2)

    # New format: /playlists/lk.<uuid> (not enough info to call users_playlists)
    m = re.search(r'music\.yandex\.(?:ru|com)/playlists/(lk\.[^/]+)$', url)
    if m:
        return "lk", m.group(1)

    return None, None


def _yt_dlp_items_from_url(user_input: str):
    """Use yt-dlp to extract entries (works for many sites; not all Spotify cases are extractable)."""
    raw = (user_input or "").strip()
    if not raw:
        return None

    url = raw if raw.startswith("http") else (_first_url_from_text(raw) or raw)
    url = _clean_url_for_ydl(url)

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "ignoreerrors": True,
    }

    # Use cookies if present (helps for some sites; harmless otherwise)
    if os.path.exists("cookies.txt"):
        ydl_opts["cookiefile"] = "cookies.txt"

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        logging.error(f"yt-dlp extract error: {e}")
        return None

    if not info:
        return None

    entries = info.get("entries")
    if not entries:
        # Not a playlist? Treat as a single item.
        title = info.get("title")
        if not title:
            return None
        thumb = info.get("thumbnail") or ""
        return [{"title": title, "thumbnail": thumb, "id": info.get("id") or title}]

    items = []
    idx = 0
    for e in entries:
        if not e:
            continue
        title = e.get("title") or e.get("fulltitle") or e.get("id")
        if not title:
            continue
        thumb = e.get("thumbnail") or ""

        # yt-dlp with extract_flat often doesn't include thumbnails for YouTube playlists.
        # We can reliably derive a thumbnail URL from the video id.
        if not thumb:
            ie_key = (e.get("ie_key") or info.get("extractor_key") or "").lower()
            vid = e.get("id") or ""
            if ("youtube" in ie_key) and re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
                thumb = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
        idx += 1
        items.append({"title": title, "thumbnail": thumb, "id": e.get("id") or f"{idx}"})

    return items if items else None

def get_playlist_info(playlist_url, ym_token_override: str = None):
    """Route to the right fetcher based on URL."""
    try:
        raw = (playlist_url or "").strip()

        # Spotify path
        if _is_spotify_url(raw):
            return _spotify_items_from_url(raw)

        # Yandex Music path
        user_id, playlist_id = extract_yandex_playlist_info(raw)
        if user_id and playlist_id:
            if user_id == "lk":
                logging.error("Ссылка вида /playlists/lk.* не содержит owner/id для API. Нужен iframe.")
                return None

            ym_token = ym_token_override or os.getenv("YM_TOKEN")
            client = Client(ym_token) if ym_token else Client()
            client.init()

            playlist = client.users_playlists(playlist_id, user_id=user_id)
            if not playlist:
                logging.error("Плейлист не найден")
                return None

            items = []
            for track_short in playlist.tracks:
                try:
                    track = track_short.track
                    if not track:
                        continue
                    title = track.title or "Без названия"
                    artists = ", ".join(a.name for a in track.artists) if track.artists else "Unknown"
                    cover_uri = None
                    if hasattr(track, "cover_uri") and track.cover_uri:
                        cover_uri = f"https://{track.cover_uri.replace('%%', '400x400')}"
                    elif hasattr(track, "albums") and track.albums and track.albums[0].cover_uri:
                        cover_uri = f"https://{track.albums[0].cover_uri.replace('%%', '400x400')}"
                    items.append({
                        "title": f"{title} - {artists}",
                        "thumbnail": cover_uri or "",
                        "id": track.id,
                    })
                except Exception as track_error:
                    logging.error(f"Track error: {track_error}")
                    continue
            return items if items else None

        # Fallback: yt-dlp (YouTube, SoundCloud, etc.)
        return _yt_dlp_items_from_url(playlist_url)

    except Exception as e:
        logging.error(f"Playlist error: {e}")
        return None

@app.route("/", methods=["GET", "POST"])
def index():
    playlist_data = None
    error_message = None

    if request.method == "POST":
        playlist_url = request.form.get("playlist_url", "").strip()
        ym_token = request.form.get("ym_token", "").strip() or None

        if not playlist_url:
            error_message = "Please enter a playlist URL."
        else:
            playlist_data = get_playlist_info(playlist_url, ym_token_override=ym_token)

            if not playlist_data:
                error_message = (
                    "Could not load playlist. Check:<br>"
                    "- The playlist is public<br>"
                    "- The URL is correct<br>"
                    "- For Yandex Music private playlists: paste your YM Token in the settings below<br>"
                    "- For Spotify: set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET env vars<br><br>"
                    "Supported formats:<br>"
                    "- <code>https://open.spotify.com/playlist/...</code><br>"
                    "- <code>https://music.yandex.ru/users/USER/playlists/ID</code><br>"
                    "- <code>https://music.yandex.ru/iframe/playlist/USER/ID</code><br>"
                    "- YouTube, SoundCloud, and anything supported by yt-dlp<br>"
                    "- For Yandex <code>/playlists/lk.*</code> links, paste the iframe embed code instead."
                )
            else:
                playlist_data = [
                    {"index": i + 1, "title": t["title"], "thumbnail": t["thumbnail"], "id": t["id"]}
                    for i, t in enumerate(playlist_data)
                ]

    playlist_url = request.form.get("playlist_url", "").strip() if request.method == "POST" else ""

    return render_template(
        "index.html",
        playlist_data=playlist_data,
        error_message=error_message,
        playlist_url=playlist_url,
    )

if __name__ == '__main__':
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)