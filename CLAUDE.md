# Playlist Tier List Maker — Agent Instructions

A Flask web app that loads a music playlist and turns it into a drag-and-drop tier list. Tracks are shown as cards with album art; the user drags them into S/A/B/C/D/F tiers and exports the result as a JPEG.

---

## Stack

- **Backend**: Python 3 / Flask (`app.py`)
- **Frontend**: Single Jinja2 template (`templates/index.html`), vanilla JS, Bootstrap 4
- **Playlist fetching**: `spotipy` (Spotify official API), `requests` (Spotify anon token), `yandex-music` (Yandex Music), `yt-dlp` (YouTube, SoundCloud, etc.)
- **Deployment**: Docker + docker-compose, Nginx reverse proxy

## Key files

| File | Purpose |
|------|---------|
| `app.py` | All backend logic — URL routing, playlist fetchers, Flask routes |
| `templates/index.html` | Entire UI including inline JS (drag-drop, tier management, localStorage, export) |
| `static/styles.css` | Dark theme styles |
| `requirements.txt` | Python deps |
| `Dockerfile` | Container build (python:3.12-slim) |
| `docker-compose.yml` | Production deployment — binds to 127.0.0.1:5000 |
| `nginx/` | Nginx reverse proxy config |
| `.env.example` | All supported environment variables with descriptions |

---

## How playlist fetching works

`get_playlist_info(url, ym_token_override)` in `app.py` dispatches to one of three fetchers:

1. **Spotify** — `_spotify_items_from_url()`:
   - Tries official `spotipy` API first if `SPOTIFY_CLIENT_ID` + `SPOTIFY_CLIENT_SECRET` are set
   - Falls back to anonymous web-player token via `_spotify_anon_token()`
   - Anonymous token request uses `SPOTIFY_DC_COOKIE` env var (`sp_dc` cookie from browser) — required because Spotify blocks datacenter IPs without it
   - Uses `_spotify_fetch_with_token()` to paginate through tracks via Web API

2. **Yandex Music** — `extract_yandex_playlist_info()` parses the URL, then `yandex_music.Client` fetches tracks. Token priority: `ym_token_override` (from browser UI) → `YM_TOKEN` env var → unauthenticated (hits captcha)

3. **Everything else** — `_yt_dlp_items_from_url()` via yt-dlp. Works for YouTube, SoundCloud, etc.

---

## Production server

- **Provider**: VPS in Netherlands (Aeza or similar)
- **OS**: Ubuntu/Debian
- **Docker**: installed via `curl -fsSL https://get.docker.com | sh`
- **Compose**: older version — use `docker-compose` (with hyphen), not `docker compose`
- **Repo location on server**: `~/Playlist-to-Tier-List`
- **App runs on**: `127.0.0.1:5000` behind Nginx

---

## Install on a fresh VPS

```bash
# 1. Install Docker
curl -fsSL https://get.docker.com | sh

# 2. Clone repo
git clone https://github.com/StarecMudrec/Playlist-to-Tier-List.git
cd Playlist-to-Tier-List

# 3. Configure environment — edit docker-compose.yml
nano docker-compose.yml
# Add under `environment:`:
#   - SPOTIFY_DC_COOKIE=your_sp_dc_value
#   - YM_TOKEN=your_ym_token (optional)

# 4. Build and start
docker-compose up -d --build

# 5. Verify
curl http://localhost:5000
```

---

## Configure environment variables

Edit `docker-compose.yml` on the server:

```yaml
services:
  web:
    build: .
    ports:
      - "127.0.0.1:5000:5000"
    environment:
      - PORT=5000
      - SPOTIFY_DC_COOKIE=your_sp_dc_value_here
      - YM_TOKEN=your_ym_token_here
      # - FLASK_DEBUG=1
```

### Getting SPOTIFY_DC_COOKIE

1. Open [open.spotify.com](https://open.spotify.com) in a browser and log in
2. F12 → **Application** → **Cookies** → `https://open.spotify.com`
3. Copy the value of the `sp_dc` cookie
4. Paste into `docker-compose.yml` as `SPOTIFY_DC_COOKIE`

The `sp_dc` cookie is long-lived (months). When Spotify stops working, it has likely expired — repeat the steps above.

### Getting YM_TOKEN (Yandex Music)

Install the [yandex-music-token browser extension](https://github.com/MarshalX/yandex-music-token) — it auto-captures the token after login. Alternatively users can paste their token directly in the UI (no server config needed).

---

## Update the app

On the server:

```bash
cd ~/Playlist-to-Tier-List
git pull
docker-compose up -d --build
```

---

## Useful maintenance commands

```bash
# View logs
docker-compose logs | tail -100

# Follow logs live
docker-compose logs -f

# Restart without rebuilding
docker-compose restart

# Stop
docker-compose down

# Check running containers
docker ps

# Check what's on port 5000
ss -tlnp | grep 5000
```

---

## Nginx setup (reverse proxy)

If serving via a domain, use Nginx to proxy `localhost:5000`. Example config in `nginx/`:

```nginx
server {
    listen 80;
    server_name yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

Reload Nginx after changes: `systemctl reload nginx`

---

## Running locally (dev)

```bash
pip install -r requirements.txt
python app.py
# open http://localhost:5000
```

## Tests

```bash
pip install pytest
python -m pytest tests/ -v
```

Tests live in `tests/test_app.py` — cover URL detection and Spotify fetcher logic (mocked).

---

## Known issues and gotchas

| Issue | Cause | Fix |
|-------|-------|-----|
| Spotify returns "Could not load" | `sp_dc` cookie expired or missing | Get fresh `sp_dc` from browser, update `docker-compose.yml`, rebuild |
| Spotify 403 on token endpoint | Datacenter IP blocked without `sp_dc` | Always set `SPOTIFY_DC_COOKIE` — anonymous access blocked from VPS IPs |
| Yandex Music captcha error | No token provided | Set `YM_TOKEN` env var or have user paste token in UI |
| yt-dlp Yandex Music broken | YM extractor broken in yt-dlp since late 2025 | Do not rely on yt-dlp for YM; use `yandex-music` library path only |
| Port 5000 already in use | Old container still running | `docker-compose down` then `docker-compose up -d --build` |
| Smart/curly quotes in app.py | Pasting code from rich-text editors | Run: `python -c "import ast; ast.parse(open('app.py').read())"` to check. Fix by replacing curly quotes with straight ASCII quotes in the file |

---

## Branch state

- `main` — production branch, always deployable
- Feature branches merged into `main` via fast-forward
