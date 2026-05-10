# Playlist-to-Tier-List
For it to work with some sites that are unavailible in your region you might want to host this site it using vpn (Currently doesn't support yandex music because of captcha)

## Docker

### Build & run (Docker)

```bash
docker build -t playlist-to-tier-list .
docker run --rm -p 5000:5000 playlist-to-tier-list
```

Открыть в браузере: `http://localhost:5000`

### Run (docker compose)

```bash
docker compose up --build
```

Теперь контейнер слушает только localhost: `http://127.0.0.1:5000/` (это нужно, чтобы не конфликтовать с другими сайтами и не светить приложение наружу).

### Nginx на сервере (только для dahole.ru)

Если на сервере уже есть Nginx с другими сайтами, добавьте отдельный server block для домена `dahole.ru` и проксируйте на `127.0.0.1:5000`.

Готовый пример лежит в репозитории: `nginx/host-dahole.ru.conf`

### Переменные окружения

- **PORT**: порт, который слушает Flask внутри контейнера (по умолчанию `5000`)
- **FLASK_DEBUG**: `1` чтобы включить debug, иначе выключен
- **YM_TOKEN**: токен Яндекс.Музыки (нужен для приватных плейлистов/”Мне нравится” и иногда при региональных ограничениях)
- **SPOTIFY_CLIENT_ID**: Client ID от Spotify developer app
- **SPOTIFY_CLIENT_SECRET**: Client Secret от Spotify developer app

#### Как настроить Spotify

**Способ 1 — `sp_dc` cookie (проще, не нужна регистрация):**

1. Открой [open.spotify.com](https://open.spotify.com) в браузере и залогинься
2. F12 → вкладка **Application** → **Cookies** → `https://open.spotify.com`
3. Найди куку `sp_dc` и скопируй её значение

Укажи в `docker-compose.yml`:

```yaml
environment:
  - SPOTIFY_DC_COOKIE=твоё_значение_sp_dc
```

**Способ 2 — официальные API credentials** (если удалось зарегистрировать app на developer.spotify.com):

```yaml
environment:
  - SPOTIFY_CLIENT_ID=твой_client_id
  - SPOTIFY_CLIENT_SECRET=твой_client_secret
```

#### Как получить YM_TOKEN

Установи расширение [yandex-music-token](https://github.com/MarshalX/yandex-music-token) для Chrome или Firefox — оно автоматически перехватит токен после входа в Яндекс Музыку. Либо пользователи могут вставить токен прямо на сайте (поле “Yandex Music Token” под формой).

### Поддержка других сайтов

Для всех сайтов **кроме Яндекс Музыки и Spotify** приложение использует **`yt-dlp`** (YouTube, SoundCloud и т.д.).