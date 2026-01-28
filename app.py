from flask import Flask, render_template, request
from yandex_music import Client
import yt_dlp
import re
import logging
from urllib.parse import urlparse
import os

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
        idx += 1
        items.append({"title": title, "thumbnail": thumb, "id": e.get("id") or f"{idx}"})

    return items if items else None

def get_playlist_info(playlist_url):
    """Yandex via yandex_music; everything else via yt-dlp."""
    try:
        user_id, playlist_id = extract_yandex_playlist_info(playlist_url)

        # Yandex path
        if user_id and playlist_id:
            if user_id == "lk":
                logging.error("Ссылка вида /playlists/lk.* не содержит owner/id для API. Нужен iframe.")
                return None

            ym_token = os.getenv("YM_TOKEN")
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
                    artists = ', '.join(artist.name for artist in track.artists) if track.artists else "Неизвестный исполнитель"

                    cover_uri = None
                    if hasattr(track, 'cover_uri') and track.cover_uri:
                        cover_uri = f"https://{track.cover_uri.replace('%%', '400x400')}"
                    elif hasattr(track, 'albums') and track.albums and track.albums[0].cover_uri:
                        cover_uri = f"https://{track.albums[0].cover_uri.replace('%%', '400x400')}"

                    items.append({
                        'title': f"{title} - {artists}",
                        'thumbnail': cover_uri or '',
                        'id': track.id
                    })
                except Exception as track_error:
                    logging.error(f"Ошибка обработки трека: {track_error}")
                    continue

            return items if items else None

        # Non-Yandex path (yt-dlp)
        return _yt_dlp_items_from_url(playlist_url)

    except Exception as e:
        logging.error(f"Playlist error: {str(e)}")
        return None

@app.route('/', methods=['GET', 'POST'])
def index():
    playlist_data = None
    error_message = None
    
    if request.method == 'POST':
        playlist_url = request.form.get('playlist_url', '').strip()
        
        if not playlist_url:
            error_message = "Введите ссылку на плейлист"
        else:
            playlist_data = get_playlist_info(playlist_url)
            
            if not playlist_data:
                error_message = """Не удалось загрузить плейлист. Проверьте:<br>
                - Доступность плейлиста<br>
                - Правильность ссылки<br>
                - Для приватных плейлистов требуется авторизация<br><br>
                Поддерживаемые форматы:<br>
                - https://music.yandex.ru/users/USER/playlists/ID<br>
                - https://music.yandex.ru/iframe/playlist/USER/ID<br>
                - или вставьте iframe-код (приложение само вытащит ссылку)<br>
                - Любые ссылки/плейлисты, которые умеет yt-dlp (YouTube/SoundCloud/и т.д.)<br>
                <br>
                Если у вас ссылка вида /playlists/lk.... — вставьте iframe-код плейлиста (как в “Поделиться”).<br>
                Примечание: Spotify сейчас не поддерживается через yt-dlp (DRM)."""
            else:
                playlist_data = [{
                    'index': idx + 1,
                    'title': track['title'],
                    'thumbnail': track['thumbnail'],
                    'id': track['id']
                } for idx, track in enumerate(playlist_data)]
    
    return render_template('index.html',
                        playlist_data=playlist_data,
                        error_message=error_message)

if __name__ == '__main__':
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)