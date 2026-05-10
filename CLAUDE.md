# Playlist Tier List Maker

A Flask web app that loads a music playlist and turns it into a drag-and-drop tier list. Tracks are shown as cards with album art; the user drags them into S/A/B/C/D/F tiers and exports the result as a JPEG.

## Stack

- **Backend**: Python 3 / Flask (`app.py`)
- **Frontend**: Single Jinja2 template (`templates/index.html`), vanilla JS, Bootstrap 4
- **Playlist fetching**: `spotipy` (Spotify), `yandex-music` (Yandex Music), `yt-dlp` (YouTube, SoundCloud, everything else)
- **Deployment**: Docker + docker-compose, Nginx reverse proxy

## Key files

| File | Purpose |
|------|---------|
| `app.py` | All backend logic — URL routing, playlist fetchers, Flask routes |
| `templates/index.html` | Entire UI including inline JS (drag-drop, tier management, localStorage, export) |
| `static/styles.css` | Dark theme styles |
| `requirements.txt` | Python deps |
| `docker-compose.yml` | Production deployment |
| `.env.example` | Required environment variables (copy to `.env`) |

## How playlist fetching works

`get_playlist_info(url, ym_token_override)` in `app.py` dispatches to one of three fetchers:

1. **Spotify** — `_spotify_items_from_url()` via `spotipy` client credentials flow. Needs `SPOTIFY_CLIENT_ID` + `SPOTIFY_CLIENT_SECRET` env vars.
2. **Yandex Music** — `extract_yandex_playlist_info()` parses the URL, then `yandex_music.Client` fetches tracks. Token comes from `ym_token_override` (sent from browser localStorage via hidden form field) or `YM_TOKEN` env var.
3. **Everything else** — `_yt_dlp_items_from_url()` via yt-dlp. Works for YouTube playlists, SoundCloud, etc.

## Running locally

```bash
pip install -r requirements.txt
python app.py
# open http://localhost:5000
```

## Running with Docker

```bash
docker-compose up --build
```

## Environment variables

See `.env.example`. Key ones:

```
SPOTIFY_CLIENT_ID=...
SPOTIFY_CLIENT_SECRET=...
YM_TOKEN=...         # optional, users can also paste token in the UI
PORT=5000
FLASK_DEBUG=0
```

## Tests

```bash
pip install pytest
python -m pytest tests/ -v
```

Tests live in `tests/test_app.py` and cover URL detection and Spotify fetcher logic (mocked).

## Branch state

- `main` — stable base
- `feat/spotify-yandex-integration` — adds Spotify support + YM token UI (not yet merged)

## Known limitations

- **Spotify credentials**: As of 2025, Spotify requires an *organization* account to register a developer app. Individual accounts may be blocked on the dashboard.
- **Yandex Music captcha**: Without a valid token the client hits captcha. Users should get a token via the [yandex-music-token browser extension](https://github.com/MarshalX/yandex-music-token).
- **yt-dlp Yandex Music extractor**: Broken as of late 2025 (502 errors) — do not rely on it as a fallback for YM.
- **Spotify DRM**: yt-dlp cannot extract Spotify — only the Spotipy API path works.
- **Smart quotes**: When editing `app.py`, make sure your editor uses straight ASCII quotes. The file was previously corrupted by curly quotes from a plan document and had to be fixed with a binary replace.
