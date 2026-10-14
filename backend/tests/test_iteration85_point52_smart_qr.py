"""Point 52 (Sep 2026): single smart QR routes iPhone → App Store,
Android → Play Store. Verify User-Agent classifier."""
import importlib.util, sys, pathlib
_spec = importlib.util.spec_from_file_location(
    "server_mod", pathlib.Path(__file__).parent.parent / "server.py"
)
_mod = importlib.util.module_from_spec(_spec)
# Only load top-of-file symbols we care about; stop before FastAPI startup side-effects.
# Easiest: just read the file and exec the three definitions in isolation.
_src = (pathlib.Path(__file__).parent.parent / "server.py").read_text()
_ns = {"__name__": "server_mod_shim"}
# Extract the two URL constants and the resolver function block.
import re as _re
_url_m = _re.search(r"^PLAY_STORE_URL = .*?^APP_STORE_URL\s*=.*?$", _src, _re.S | _re.M)
_fn_m = _re.search(r"^def _resolve_store_from_ua\(.*?return \"other\", PLAY_STORE_URL  # default fallback keeps old behaviour", _src, _re.S | _re.M)
assert _url_m and _fn_m, "could not locate Point 52 symbols in server.py"
exec(_url_m.group(0), _ns)
exec(_fn_m.group(0), _ns)
_resolve_store_from_ua = _ns["_resolve_store_from_ua"]
PLAY_STORE_URL = _ns["PLAY_STORE_URL"]
APP_STORE_URL = _ns["APP_STORE_URL"]


def test_iphone_goes_to_app_store():
    ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1"
    platform, url = _resolve_store_from_ua(ua)
    assert platform == "ios" and url == APP_STORE_URL


def test_ipad_goes_to_app_store():
    ua = "Mozilla/5.0 (iPad; CPU OS 17_2 like Mac OS X) AppleWebKit/605.1.15"
    platform, url = _resolve_store_from_ua(ua)
    assert platform == "ios" and url == APP_STORE_URL


def test_ipad_masquerade_still_app_store():
    """iPadOS 13+ masquerades as 'Macintosh' + Mobile."""
    ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Mobile Safari/605.1.15"
    platform, url = _resolve_store_from_ua(ua)
    assert platform == "ios" and url == APP_STORE_URL


def test_android_goes_to_play_store():
    ua = "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 Chrome/126.0.0.0 Mobile Safari/537.36"
    platform, url = _resolve_store_from_ua(ua)
    assert platform == "android" and url == PLAY_STORE_URL


def test_desktop_falls_back_to_play_store():
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64) Chrome/126.0.0.0 Safari/537.36"
    platform, url = _resolve_store_from_ua(ua)
    assert platform == "other" and url == PLAY_STORE_URL


def test_empty_ua_falls_back_to_play_store():
    platform, url = _resolve_store_from_ua("")
    assert platform == "other" and url == PLAY_STORE_URL
