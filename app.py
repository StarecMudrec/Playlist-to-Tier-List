from flask import Flask, render_template, request
from yandex_music import Client
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import re
import logging
from urllib.parse import urlparse
import os

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

def _first_supported_url_from_text(text: str) -> str | None:
    """
    If the user pastes an <iframe ...> snippet or any text that contains supported links,
    grab the first relevant URL (Yandex Music / Spotify).
    """
    m = re.search(r'https?://(?:music\.yandex\.(?:ru|com)|open\.spotify\.com)/[^"\s<>]+', text)
    return m.group(0) if m else None


def _clean_url(url: str) -> str:
    """Remove query params / fragments so regex matching is stable."""
    parsed = urlparse(url)
    return parsed._replace(query="", fragment="").geturl()


def extract_playlist_info(user_input: str):
    """
    Detect provider + extract IDs from:

    Yandex Music:
    - https://music.yandex.ru/users/<user>/playlists/<id>
    - https://music.yandex.ru/iframe/playlist/<user>/<id>
    - <iframe ... src="...">...</iframe>  (we'll pull the URL out)

    Note: links like /playlists/lk.<uuid> don't contain the owner+numeric id; for those,
    ask the user to paste the iframe snippet (it includes /iframe/playlist/<user>/<id>).

    Spotify:
    - https://open.spotify.com/playlist/<id>
    - https://open.spotify.com/embed/playlist/<id>
    - <iframe ... src="...">...</iframe>
    """
    raw = (user_input or "").strip()
    if not raw:
        return None, None, None

    url = raw if raw.startswith("http") else (_first_supported_url_from_text(raw) or raw)
    url = _clean_url(url)

    # Spotify
    m = re.search(r'open\.spotify\.com/(?:embed/)?playlist/([A-Za-z0-9]+)$', url)
    if m:
        return "spotify", None, m.group(1)

    # /users/<user>/playlists/<id>
    m = re.search(r'music\.yandex\.(?:ru|com)/users/([^/]+)/playlists/([^/]+)$', url)
    if m:
        return "yandex", m.group(1), m.group(2)

    # /iframe/playlist/<user>/<id>
    m = re.search(r'music\.yandex\.(?:ru|com)/iframe/playlist/([^/]+)/([^/]+)$', url)
    if m:
        return "yandex", m.group(1), m.group(2)

    # New format: /playlists/lk.<uuid> (not enough info to call users_playlists)
    m = re.search(r'music\.yandex\.(?:ru|com)/playlists/(lk\.[^/]+)$', url)
    if m:
        return "yandex", "lk", m.group(1)

    return None, None, None


def get_spotify_playlist_info(playlist_id: str):
    """Fetch Spotify playlist tracks using Client Credentials (public playlists)."""
    try:
        client_id = os.getenv("SPOTIFY_CLIENT_ID")
        client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
        if not client_id or not client_secret:
            logging.error("Missing SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET")
            return None

        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=client_id, client_secret=client_secret))

        items = []
        offset = 0
        limit = 100
        while True:
            page = sp.playlist_items(
                playlist_id,
                offset=offset,
                limit=limit,
                fields="items(track(id,name,artists(name),album(images))),next",
            )
            for it in page.get("items", []):
                track = (it or {}).get("track") or {}
                name = track.get("name")
                if not name:
                    continue
                artists = ", ".join(a.get("name") for a in (track.get("artists") or []) if a.get("name")) or "Unknown artist"
                images = (((track.get("album") or {}).get("images")) or [])
                thumb = images[0].get("url") if images else ""
                items.append(
                    {
                        "title": f"{name} - {artists}",
                        "thumbnail": thumb,
                        "id": track.get("id") or name,
                    }
                )

            if not page.get("next"):
                break
            offset += limit

        return items if items else None
    except Exception as e:
        logging.error(f"Spotify API error: {e}")
        return None

def get_playlist_info(playlist_url):
    """Get playlist info from supported providers."""
    try:
        provider, user_id, playlist_id = extract_playlist_info(playlist_url)
        if not provider or not playlist_id:
            logging.error("Неверный формат URL плейлиста")
            return None

        if provider == "spotify":
            return get_spotify_playlist_info(playlist_id)

        if provider == "yandex" and user_id == "lk":
            logging.error("Ссылка вида /playlists/lk.* не содержит owner/id для API. Нужен iframe.")
            return None

        # Инициализация клиента.
        # Для приватных плейлистов/“Мне нравится” часто требуется авторизация.
        ym_token = os.getenv("YM_TOKEN")
        client = Client(ym_token) if ym_token else Client()
        client.init()
        
        # Получаем плейлист с указанием владельца
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
                
                # Обработка данных трека
                title = track.title or "Без названия"
                artists = ', '.join(artist.name for artist in track.artists) if track.artists else "Неизвестный исполнитель"
                
                # Получаем лучшую доступную обложку
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

    except Exception as e:
        logging.error(f"Yandex Music API error: {str(e)}")
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
                - https://open.spotify.com/playlist/PLAYLIST_ID<br>
                - https://open.spotify.com/embed/playlist/PLAYLIST_ID<br>
                <br>
                Если у вас ссылка вида /playlists/lk.... — вставьте iframe-код плейлиста (как в “Поделиться”).<br>
                Для Spotify нужны переменные окружения SPOTIFY_CLIENT_ID и SPOTIFY_CLIENT_SECRET (для публичных плейлистов)."""
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