# Spotify & Yandex Music Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Spotify public playlist support via the official Web API and improve Yandex Music auth by letting users paste their token directly in the UI.

**Architecture:** Spotify playlists are fetched server-side using `spotipy` with the Client Credentials flow (no user login for public playlists); credentials come from env vars. Yandex Music already has the library wired up — we extend the frontend to let users paste a `YM_TOKEN` that is stored in localStorage and sent with each form submission, so the backend no longer depends solely on the server-side env var.

**Tech Stack:** Python 3, Flask, `spotipy` (new), `yandex-music` (existing), `yt-dlp` (existing), Jinja2 templates, vanilla JS, Bootstrap 4

---

> ⚠️ **Spotify credential caveat (May 2025):** Spotify's developer dashboard currently requires an *organization* to register a new app. If you are an individual developer, you may not be able to obtain credentials through the normal flow. Check https://developer.spotify.com/dashboard — if registration works, proceed with Task 1. If blocked, skip Task 1 and use the scraper fallback documented at the end of this plan.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `requirements.txt` | Modify | Add `spotipy` |
| `app.py` | Modify | Add `_spotify_items_from_url()`, `_is_spotify_url()`, update `get_playlist_info()`, read `ym_token` from request |
| `templates/index.html` | Modify | Add YM token settings panel (localStorage-backed), update placeholder/description copy, add Spotify to supported services |
| `tests/test_app.py` | Create | Unit tests for new routing logic and Spotify/YM parsing |

---

## Task 1: Add spotipy dependency and URL detector

**Files:**
- Modify: `requirements.txt`
- Modify: `app.py` (top of file, after existing imports)

- [ ] **Step 1: Add spotipy to requirements**

Open `requirements.txt` and replace the entire file with:

```
flask
yandex_music
yt-dlp
spotipy
```

- [ ] **Step 2: Add Spotify URL detection helper to app.py**

In `app.py`, after the existing `import os` line (line 7), add this import at the top:

```python
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
```

Then, after the `_clean_url_for_ydl` function (after line 33), add:

```python
def _is_spotify_url(url: str) -> bool:
    return bool(re.search(r'open\.spotify\.com/(playlist|album)/', url))
```

- [ ] **Step 3: Write the failing test**

Create `tests/test_app.py`:

```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import _is_spotify_url

def test_spotify_playlist_url_detected():
    assert _is_spotify_url("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M") is True

def test_spotify_album_url_detected():
    assert _is_spotify_url("https://open.spotify.com/album/4aawyAB9vmqN3uQ7FjRGTy") is True

def test_yandex_url_not_spotify():
    assert _is_spotify_url("https://music.yandex.ru/users/foo/playlists/123") is False

def test_youtube_url_not_spotify():
    assert _is_spotify_url("https://www.youtube.com/playlist?list=PLx0sYbCqOb8TBPRdmBHs5Iftvv9TPboYG") is False
```

- [ ] **Step 4: Run test to confirm it fails before implementation**

```
cd C:\Users\89651\Documents\GitHub\Playlist-to-Tier-List
python -m pytest tests/test_app.py::test_spotify_playlist_url_detected -v
```

Expected: FAIL — `ImportError` or `ModuleNotFoundError` for spotipy (not installed yet).

- [ ] **Step 5: Install spotipy**

```
pip install spotipy
```

- [ ] **Step 6: Run all four tests**

```
python -m pytest tests/test_app.py -v
```

Expected: All 4 PASS.

- [ ] **Step 7: Commit**

```
git add requirements.txt app.py tests/test_app.py
git commit -m "feat: add spotify URL detection and spotipy dependency"
```

---

## Task 2: Implement Spotify metadata fetcher

**Files:**
- Modify: `app.py` — add `_spotify_items_from_url()`, update `get_playlist_info()`

- [ ] **Step 1: Write failing tests for Spotify fetcher**

Add to `tests/test_app.py`:

```python
from unittest.mock import patch, MagicMock
from app import _spotify_items_from_url

def test_spotify_returns_none_without_credentials(monkeypatch):
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_SECRET", raising=False)
    result = _spotify_items_from_url("https://open.spotify.com/playlist/abc123")
    assert result is None

def test_spotify_returns_none_for_non_spotify_url(monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "fake_id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "fake_secret")
    result = _spotify_items_from_url("https://soundcloud.com/user/track")
    assert result is None

def test_spotify_returns_tracks(monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "fake_id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "fake_secret")

    fake_page = {
        "items": [
            {
                "track": {
                    "id": "track1",
                    "name": "Song A",
                    "artists": [{"name": "Artist X"}],
                    "album": {"images": [{"url": "https://example.com/img.jpg"}]},
                }
            }
        ],
        "next": None,
    }

    mock_sp = MagicMock()
    mock_sp.playlist_tracks.return_value = fake_page

    with patch("app.spotipy.Spotify", return_value=mock_sp), \
         patch("app.SpotifyClientCredentials"):
        result = _spotify_items_from_url("https://open.spotify.com/playlist/abc123")

    assert result is not None
    assert len(result) == 1
    assert result[0]["title"] == "Song A - Artist X"
    assert result[0]["thumbnail"] == "https://example.com/img.jpg"
    assert result[0]["id"] == "track1"
```

- [ ] **Step 2: Run tests to confirm they fail**

```
python -m pytest tests/test_app.py::test_spotify_returns_none_without_credentials tests/test_app.py::test_spotify_returns_tracks -v
```

Expected: FAIL — `ImportError: cannot import name '_spotify_items_from_url'`.

- [ ] **Step 3: Implement `_spotify_items_from_url` in app.py**

Add this function after the `_is_spotify_url` helper you added in Task 1:

```python
def _spotify_items_from_url(url: str):
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    if not client_id or not client_secret:
        logging.warning("Spotify credentials not set — skipping Spotify fetch")
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
```

- [ ] **Step 4: Wire Spotify into `get_playlist_info`**

In `app.py`, replace the `get_playlist_info` function (lines 133–186) with:

```python
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
```

- [ ] **Step 5: Update the Flask route to pass `ym_token_override`**

Replace the `index()` view (lines 188–227) with:

```python
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
                    "- For Yandex Music private playlists: paste your YM Token below<br>"
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
```

- [ ] **Step 6: Run all tests**

```
python -m pytest tests/test_app.py -v
```

Expected: All 7 tests PASS.

- [ ] **Step 7: Commit**

```
git add app.py tests/test_app.py
git commit -m "feat: add Spotify playlist fetching via spotipy client credentials"
```

---

## Task 3: Add YM Token UI (localStorage-backed)

**Files:**
- Modify: `templates/index.html`

The user pastes their Yandex Music token into a settings panel. It's saved to `localStorage` so they don't have to re-enter it. The token is injected into the hidden form field on submit.

- [ ] **Step 1: Add the settings panel HTML**

In `templates/index.html`, after the closing `</form>` tag (currently around line 49), add:

```html
<!-- YM Token Settings -->
<details id="ym-settings" class="mt-3" style="color: #ccc;">
    <summary style="cursor: pointer; user-select: none;">Yandex Music Token (for private playlists)</summary>
    <div class="mt-2">
        <p class="small text-muted">
            Obtain your token via the
            <a href="https://github.com/MarshalX/yandex-music-token" target="_blank" rel="noopener">yandex-music-token browser extension</a>.
            It is stored only in your browser.
        </p>
        <input type="text" id="ym-token-input" class="form-control" placeholder="Paste YM token here" style="max-width: 480px; font-family: monospace; font-size: 12px;">
        <button type="button" id="save-ym-token" class="btn btn-sm btn-outline-secondary mt-2">Save token</button>
        <button type="button" id="clear-ym-token" class="btn btn-sm btn-outline-danger mt-2 ml-2">Clear token</button>
        <span id="ym-token-status" class="small ml-2"></span>
    </div>
</details>
```

- [ ] **Step 2: Add a hidden input to the form**

Inside the `<form method="post">` element (currently line 39), add this hidden input right before the closing `</form>` tag:

```html
<input type="hidden" id="ym-token-hidden" name="ym_token" value="">
```

- [ ] **Step 3: Add JS to wire localStorage to the form**

In `templates/index.html`, inside the `<script>` block (near the bottom of the file), add this before any existing JS:

```javascript
// YM Token persistence
(function () {
    const KEY = "ym_token";
    const input = document.getElementById("ym-token-input");
    const hidden = document.getElementById("ym-token-hidden");
    const status = document.getElementById("ym-token-status");
    const saveBtn = document.getElementById("save-ym-token");
    const clearBtn = document.getElementById("clear-ym-token");

    function loadToken() {
        const t = localStorage.getItem(KEY) || "";
        if (input) input.value = t;
        if (hidden) hidden.value = t;
        if (status) status.textContent = t ? "Token saved." : "";
    }

    if (saveBtn) {
        saveBtn.addEventListener("click", function () {
            const t = (input ? input.value : "").trim();
            localStorage.setItem(KEY, t);
            if (hidden) hidden.value = t;
            if (status) status.textContent = t ? "Token saved." : "Token cleared.";
        });
    }

    if (clearBtn) {
        clearBtn.addEventListener("click", function () {
            localStorage.removeItem(KEY);
            if (input) input.value = "";
            if (hidden) hidden.value = "";
            if (status) status.textContent = "Token cleared.";
        });
    }

    // Populate hidden field before form submit so the token is always sent
    const form = document.querySelector("form.playlist-form");
    if (form) {
        form.addEventListener("submit", function () {
            const t = localStorage.getItem(KEY) || "";
            if (hidden) hidden.value = t;
        });
    }

    loadToken();
})();
```

- [ ] **Step 4: Update the subtitle copy**

In `templates/index.html`, find the line (currently line 36):

```html
<div class="text-muted small">Paste a Yandex Music playlist link or an iframe snippet, then drag tracks into tiers.</div>
```

Replace with:

```html
<div class="text-muted small">Paste a Spotify or Yandex Music playlist link, or any YouTube / SoundCloud playlist, then drag tracks into tiers.</div>
```

- [ ] **Step 5: Manually test the UI**

Start the Flask dev server:
```
python app.py
```

Open http://localhost:5000 in a browser and verify:
- The "Yandex Music Token" details panel is visible and expands on click
- Pasting a token and clicking "Save token" shows "Token saved."
- Refreshing the page restores the token in the input (localStorage persisted)
- Submitting a Yandex Music URL sends the hidden `ym_token` field (inspect Network tab → Form Data)
- Submitting a Spotify URL routes correctly (will fail gracefully if no env vars set)
- Clicking "Clear token" removes it and shows "Token cleared."

- [ ] **Step 6: Commit**

```
git add templates/index.html
git commit -m "feat: add YM token settings panel with localStorage persistence"
```

---

## Task 4: Set up environment variables and smoke-test Spotify

**Files:**
- Create: `.env.example` (documentation only — never committed with real values)

- [ ] **Step 1: Create .env.example**

Create `.env.example` at the project root:

```
# Spotify Web API credentials
# Register your app at https://developer.spotify.com/dashboard
SPOTIFY_CLIENT_ID=your_client_id_here
SPOTIFY_CLIENT_SECRET=your_client_secret_here

# Yandex Music token (optional — users can also paste it in the UI)
# Obtain via https://github.com/MarshalX/yandex-music-token
YM_TOKEN=your_ym_token_here

# Flask config
PORT=5000
FLASK_DEBUG=0
```

- [ ] **Step 2: Verify .env.example is not tracked by git**

Check `.gitignore` — if `.env` files are not already ignored, add:

```
.env
.env.local
```

Do NOT add `.env.example` to `.gitignore` — it should be committed as documentation.

- [ ] **Step 3: Set credentials and smoke-test Spotify**

In your terminal, set env vars and run the server:

```
$env:SPOTIFY_CLIENT_ID = "your_real_client_id"
$env:SPOTIFY_CLIENT_SECRET = "your_real_client_secret"
python app.py
```

Then open http://localhost:5000 and load a public Spotify playlist, e.g.:
```
https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M
```

Expected: Track cards appear in the "Unsorted" pool. Each card shows the album art thumbnail and track name + artist.

- [ ] **Step 4: Commit**

```
git add .env.example .gitignore
git commit -m "docs: add .env.example with Spotify and YM credential instructions"
```

---

## Fallback: Spotify without credentials (SpotifyScraper)

> Use this only if you cannot obtain Spotify API credentials. This approach violates Spotify's ToS and is for personal/educational use only.

If `SPOTIFY_CLIENT_ID` is not set, you can fall back to `spotifyscraper`:

```
pip install spotifyscraper
```

Add to `requirements.txt`: `spotifyscraper`

Add to `app.py`, inside `_spotify_items_from_url`, after the credentials check:

```python
# If no credentials, try scraper fallback (personal use only — violates ToS)
if not client_id or not client_secret:
    try:
        from spotifyscraper import SpotifyScraper
        scraper = SpotifyScraper()
        m = re.search(r'open\.spotify\.com/playlist/([A-Za-z0-9]+)', url)
        if not m:
            return None
        playlist = scraper.get_playlist(m.group(1))
        return [
            {"title": f"{t.name} - {t.artist}", "thumbnail": t.image_url or "", "id": t.id}
            for t in playlist.tracks
        ]
    except Exception as e:
        logging.error(f"SpotifyScraper fallback error: {e}")
        return None
```

---

## Self-Review

**Spec coverage check:**
- ✅ Spotify public playlists — Task 2 (`_spotify_items_from_url` with `playlist_tracks`)
- ✅ Spotify albums — Task 2 (`album_tracks` branch)
- ✅ Spotify pagination — Task 2 (`sp.next(page)` loop)
- ✅ Yandex Music token from UI — Task 3 (localStorage + hidden field)
- ✅ Yandex Music token from env var still works — Task 2 (`ym_token_override or os.getenv("YM_TOKEN")`)
- ✅ yt-dlp fallback preserved — Task 2 (last branch in `get_playlist_info`)
- ✅ Error messages updated to English with Spotify info — Task 2
- ✅ Credential documentation — Task 4

**Placeholder scan:** None found — all steps contain complete code.

**Type consistency:**
- `_spotify_items_from_url` returns `list[dict] | None` — matches what `get_playlist_info` expects and what `_yt_dlp_items_from_url` returns ✅
- `ym_token_override: str = None` in `get_playlist_info` — matched in Flask route `request.form.get("ym_token", "").strip() or None` ✅
- Hidden field `name="ym_token"` matches `request.form.get("ym_token")` ✅

---

**Plan complete and saved to `docs/superpowers/plans/2026-05-10-spotify-yandex-music-integration.md`.**

**Two execution options:**

**1. Subagent-Driven (recommended)** — Fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
