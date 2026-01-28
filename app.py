from flask import Flask, render_template, request
from yandex_music import Client
import re
import logging
from urllib.parse import urlparse
import os

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

def extract_playlist_info(url):
    """Извлекаем user_id и playlist_id из URL с улучшенной валидацией"""
    # Пример URL: https://music.yandex.ru/users/USER_ID/playlists/PLAYLIST_ID
    pattern = r'yandex\.(?:com|ru)/users/([^/]+)/playlists/([a-f0-9-]+)'
    match = re.search(pattern, url)
    if match:
        return match.group(1), match.group(2)
    return None, None

def get_playlist_info(playlist_url):
    """Получаем информацию о плейлисте с современным API"""
    try:
        user_id, playlist_id = extract_playlist_info(playlist_url)
        if not user_id or not playlist_id:
            logging.error("Неверный формат URL плейлиста")
            return None

        # Инициализация клиента с современными параметрами
        client = Client()
        
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
        elif '/users/' not in playlist_url or '/playlists/' not in playlist_url:
            error_message = """Неверный формат ссылки. Используйте ссылку вида:<br>
            https://music.yandex.ru/users/ВАШ_ID/playlists/ID_ПЛЕЙЛИСТА"""
        else:
            playlist_data = get_playlist_info(playlist_url)
            
            if not playlist_data:
                error_message = """Не удалось загрузить плейлист. Проверьте:<br>
                - Доступность плейлиста<br>
                - Правильность ссылки<br>
                - Для приватных плейлистов требуется авторизация"""
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