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
- **YM_TOKEN**: токен Яндекс.Музыки (нужен для приватных плейлистов/“Мне нравится” и иногда при региональных ограничениях)