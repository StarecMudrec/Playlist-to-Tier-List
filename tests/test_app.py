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
