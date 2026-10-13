import time
import json
import pytest
from app import app, jobs


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_homepage_serves_html(client):
    res = client.get("/")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Clip Saver" in html
    assert "Save any video, in the quality you choose" in html
    assert "/static/fonts/source-serif-4" in html
    assert "/static/fonts/inter" in html
    # Ensure no emojis in HTML
    for char in html:
        # Check high unicode surrogate/emoji ranges
        cp = ord(char)
        assert not (0x1F300 <= cp <= 0x1FAFF or 0x2600 <= cp <= 0x27BF), f"Found emoji: {char}"


def test_api_info_unsupported_domain(client):
    res = client.post("/api/info", json={"url": "https://vimeo.com/123456"})
    assert res.status_code == 400
    data = res.get_json()
    assert "Unsupported platform" in data["error"]


def test_api_info_insecure_scheme(client):
    res = client.post("/api/info", json={"url": "http://youtube.com/watch?v=123"})
    assert res.status_code == 400
    data = res.get_json()
    assert "Only secure HTTPS links are supported" in data["error"]


def test_api_info_valid_youtube(client):
    url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    res = client.post("/api/info", json={"url": url})
    assert res.status_code == 200
    data = res.get_json()
    assert "title" in data
    assert "thumbnail" in data
    assert "uploader" in data
    assert "qualities" in data
    assert len(data["qualities"]) > 0
    # Must contain audio option
    has_audio = any(q["id"] == "audio" for q in data["qualities"])
    assert has_audio is True


def test_api_prepare_and_progress_flow(client):
    url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    # Start prepare job with audio
    prep_res = client.post("/api/prepare", json={"url": url, "quality": "audio"})
    assert prep_res.status_code == 200
    prep_data = prep_res.get_json()
    job_id = prep_data["job_id"]
    assert job_id is not None

    # Poll progress until ready or timeout (max 45 seconds for short test video)
    max_wait = 45
    start = time.time()
    final_info = None

    while time.time() - start < max_wait:
        prog_res = client.get(f"/api/progress/{job_id}")
        assert prog_res.status_code == 200
        prog_data = prog_res.get_json()
        assert "state" in prog_data
        assert "percent" in prog_data
        assert "message" in prog_data

        if prog_data["state"] in ("ready", "error"):
            final_info = prog_data
            break
        time.sleep(1)

    assert final_info is not None, "Job timed out"
    assert final_info["state"] == "ready", f"Job failed with message: {final_info.get('message')}"
    assert final_info["percent"] == 100.0

    # Test file retrieval
    file_res = client.get(f"/api/file/{job_id}")
    assert file_res.status_code == 200
    assert file_res.headers.get("Content-Disposition") is not None
    assert "attachment" in file_res.headers.get("Content-Disposition")
    assert len(file_res.data) > 1000  # Non-empty media data
