import os
import io
import subprocess
import pytest
from app import app, probe_media


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def sample_video_bytes():
    # Generate 3-second test mp4 via ffmpeg
    temp_path = "temp_fixture_video.mp4"
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=3:size=320x240:rate=25", temp_path]
    subprocess.run(cmd, capture_output=True)
    with open(temp_path, "rb") as f:
        data = f.read()
    if os.path.exists(temp_path):
        os.remove(temp_path)
    return data


def test_crop_upload_invalid_file(client):
    res = client.post("/api/crop/upload", data={})
    assert res.status_code == 400
    assert "No media file" in res.get_json()["error"]


def test_crop_upload_unsupported_extension(client):
    data = {"file": (io.BytesIO(b"fake data"), "test.exe")}
    res = client.post("/api/crop/upload", data=data, content_type="multipart/form-data")
    assert res.status_code == 400
    assert "Unsupported format" in res.get_json()["error"]


def test_crop_upload_valid_and_process_flow(client, sample_video_bytes):
    # Upload
    upload_data = {
        "file": (io.BytesIO(sample_video_bytes), "sample_test.mp4")
    }
    upload_res = client.post("/api/crop/upload", data=upload_data, content_type="multipart/form-data")
    assert upload_res.status_code == 200
    info = upload_res.get_json()
    assert "file_id" in info
    assert info["is_video"] is True
    assert info["duration"] > 2.0
    file_id = info["file_id"]

    # Preview stream
    prev_res = client.get(f"/api/crop/preview/{file_id}")
    assert prev_res.status_code in (200, 206)
    assert len(prev_res.data) > 1000

    # Process crop (e.g. from 0.5s to 2.0s)
    crop_res = client.post("/api/crop/process", json={
        "file_id": file_id,
        "start_time": 0.5,
        "end_time": 2.0
    })
    assert crop_res.status_code == 200
    crop_info = crop_res.get_json()
    crop_id = crop_info["crop_id"]
    assert "download_url" in crop_info

    # Download cropped file
    dl_res = client.get(f"/api/crop/download/{crop_id}")
    assert dl_res.status_code == 200
    assert "attachment" in dl_res.headers.get("Content-Disposition")
    assert len(dl_res.data) > 500
