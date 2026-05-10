from flask import Flask, render_template, request, redirect, url_for
from yandex_music import Client
import yt_dlp
import re
import logging
import json
import time
from urllib.parse import urlparse, urlencode
import os
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import requests

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# --- Spotify OAuth token management ---

_SPOTIFY_TOKEN_FILE = "spotify_token.json"
_spotify_token_cache = {}


def _save_spotify_tokens(tokens: dict):
    global _spotify_token_cache
    refresh_token = tokens.get("refresh_token") or _spotify_token_cache.get("refresh_token")
    _spotify_token_cache = {
        "access_token": tokens["access_token"],
        "refresh_token": refresh_token,
        "expires_at": time.time() + tokens.get("expires_in", 3600) - 60,
    }
    try:
        with open(_SPOTIFY_TOKEN_FILE, "w") as f:
            json.dump(_spotify_token_cache, f)
    except Exception as e:
        logging.warning(f"Could not save Spotify token file: {e}")


def _get_spotify_oauth_token() -> str | None:
    global _spotify_token_cache
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None

    # Load from disk if in-memory cache is empty
    if not _spotify_token_cache and os.path.exists(_SPOTIFY_TOKEN_FILE):
        try:
            with open(_SPOTIFY_TOKEN_FILE) as f:
                _spotify_token_cache = json.load(f)
        except Exception:
            pass

    if not _spotify_token_cache.get("refresh_token"):
        return None

    # Refresh access token if expired
    if time.time() >= _spotify_token_cache.get("expires_at", 0):
        try:
            r = requests.post(
                "https://accounts.spotify.com/api/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": _spotify_token_cache["refresh_token"],
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                timeout=10,
            )
            r.raise_for_status()
            _save_spotify_tokens(r.json())
        except Exception as e:
            logging.warning(f"Spotify token refresh failed: {e}")
            return None

    return _spotify_token_cache.get("access_token")


def spotify_is_connected() -> bool:
    return bool(_spotify_token_cache.get("refresh_token") or os.path.exists(_SPOTIFY_TOKEN_FILE))


# --- Spotify OAuth routes ---

@app.route("/spotify/login")
def spotify_login():
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI")
    if not client_id or not redirect_uri:
        return "SPOTIFY_CLIENT_ID and SPOTIFY_REDIRECT_URI must be set in .env", 400
    params = urlencode({
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": "playlist-read-private playlist-read-collaborative",
    })
    return redirect(f"https://accounts.spotify.com/authorize?{params}")


@app.route("/spotify/callback")
def spotify_callback():
    code = request.args.get("code")
    error = request.args.get("error")
    if error or not code:
        return redirect(url_for("index"))

    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI")

    try:
        r = requests.post(
            "https://accounts.spotify.com/api/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=10,
        )
        r.raise_for_status()
        _save_spotify_tokens(r.json())
        logging.info("Spotify OAuth: token saved successfully")
    except Exception as e:
        logging.error(f"Spotify OAuth callback error: {e}")

    return redirect(url_for("index"))


@app.route("/spotify/disconnect")
def spotify_disconnect():
    global _spotify_token_cache
    _spotify_token_cache = {}
    if os.path.exists(_SPOTIFY_TOKEN_FILE):
        os.remove(_SPOTIFY_TOKEN_FILE)
    return redirect(url_for("index"))


# --- Spotify fetching helpers ---

def _spotify_fetch_with_token(token: str, resource_type: str, resource_id: str):
    headers = {"Authorization": f"Bearer {token}"}
    items = []

    if resource_type == "playlist":
        url = f"https://api.spotify.com/v1/playlists/{resource_id}/tracks"
        params = {"limit": 100, "fields": "items(track(id,name,artists,album(images))),next"}
    else:
        url = f"https://api.spotify.com/v1/albums/{resource_id}/tracks"
        params = {"limit": 50}

    while url:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        r.raise_for_status()
        page = r.json()
        params = {}

        for item in page.get("items", []):
            track = item.get("track") or item
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
        url = page.get("next")

    return items if items else None


def _is_spotify_url(url: str) -> bool:
    return bool(re.search(r'open\.spotify\.com/(playlist|album)/', url))


def _spotify_items_from_url(url: str):
    m = re.search(r'open\.spotify\.com/(playlist|album)/([A-Za-z0-9]+)', url)
    if not m:
        return None
    resource_type, resource_id = m.group(1), m.group(2)

    # 1. Try OAuth user token (most reliable)
    token = _get_spotify_oauth_token()
    if token:
        try:
            return _spotify_fetch_with_token(token, resource_type, resource_id)
        except Exception as e:
            logging.warning(f"Spotify OAuth fetch failed: {e}")

    # 2. Try client credentials (may fail for playlists since Spotify API change Nov 2024)
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    if client_id and client_secret:
        try:
            auth = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
            sp = spotipy.Spotify(auth_manager=auth)
            items = []
            page = sp.playlist_tracks(resource_id) if resource_type == "playlist" else sp.album_tracks(resource_id)
            while page:
                for item in page.get("items", []):
                    track = item.get("track") or item
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
            if items:
                return items
        except Exception as e:
            logging.warning(f"Spotify client credentials failed: {e}")

    logging.error("All Spotify auth methods failed. Connect Spotify via /spotify/login.")
    return None


# --- Yandex URL parser ---

def _first_url_from_text(text: str) -> str | None:
    m = re.search(r'https?://[^"\s<>]+', text)
    return m.group(0) if m else None


def _clean_url_for_matching(url: str) -> str:
    parsed = urlparse(url)
    return parsed._replace(query="", fragment="").geturl()


def _clean_url_for_ydl(url: str) -> str:
    parsed = urlparse(url)
    return parsed._replace(fragment="").geturl()


def extract_yandex_playlist_info(user_input: str):
    raw = (user_input or "").strip()
    if not raw:
        return None, None

    url = raw if raw.startswith("http") else (_first_url_from_text(raw) or raw)
    url = _clean_url_for_matching(url)

    m = re.search(r'music\.yandex\.(?:ru|com)/users/([^/]+)/playlists/([^/]+)$', url)
    if m:
        return m.group(1), m.group(2)

    m = re.search(r'music\.yandex\.(?:ru|com)/iframe/playlist/([^/]+)/([^/]+)$', url)
    if m:
        return m.group(1), m.group(2)

    m = re.search(r'music\.yandex\.(?:ru|com)/playlists/(lk\.[^/]+)$', url)
    if m:
        return "lk", m.group(1)

    return None, None


def _yt_dlp_items_from_url(user_input: str):
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
        if not thumb:
            ie_key = (e.get("ie_key") or info.get("extractor_key") or "").lower()
            vid = e.get("id") or ""
            if ("youtube" in ie_key) and re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
                thumb = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
        idx += 1
        items.append({"title": title, "thumbnail": thumb, "id": e.get("id") or f"{idx}"})

    return items if items else None


def get_playlist_info(playlist_url, ym_token_override: str = None):
    try:
        raw = (playlist_url or "").strip()

        if _is_spotify_url(raw):
            return _spotify_items_from_url(raw)

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
                    "- For Spotify: click <b>Connect Spotify</b> below and log in<br>"
                    "- For Yandex Music private playlists: paste your YM Token in the settings below<br><br>"
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

    # Load token cache from disk on first request
    _get_spotify_oauth_token()

    return render_template(
        "index.html",
        playlist_data=playlist_data,
        error_message=error_message,
        playlist_url=playlist_url,
        spotify_connected=spotify_is_connected(),
        spotify_enabled=bool(os.getenv("SPOTIFY_CLIENT_ID")),
    )


if __name__ == '__main__':
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
