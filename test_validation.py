import pytest
from app import validate_url, sanitize_filename, format_bytes, format_duration


def test_allowed_hosts():
    valid_urls = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://www.tiktok.com/@user/video/1234567890",
        "https://instagram.com/reel/C123456789",
        "https://www.instagram.com/p/C123456789",
        "https://facebook.com/watch/?v=123456789",
        "https://www.facebook.com/video.php?v=123456789",
        "https://fb.watch/xyz123",
        "https://x.com/creator/status/1234567890",
        "https://twitter.com/creator/status/1234567890",
    ]
    for url in valid_urls:
        valid, msg = validate_url(url)
        assert valid is True, f"Failed for {url}: {msg}"


def test_blocked_schemes():
    blocked_urls = [
        "http://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "file:///etc/passwd",
        "ftp://youtube.com/video",
        "javascript:alert(1)",
        "data:text/html,test",
    ]
    for url in blocked_urls:
        valid, msg = validate_url(url)
        assert valid is False
        assert "secure HTTPS" in msg or "Malformed" in msg or "Unsupported" in msg


def test_blocked_hosts():
    blocked_urls = [
        "https://vimeo.com/123456",
        "https://dailymotion.com/video/x123",
        "https://evil-youtube.com/watch?v=123",
        "https://youtube.com.evil.com/video",
        "https://example.com/video.mp4",
        "https://google.com",
    ]
    for url in blocked_urls:
        valid, msg = validate_url(url)
        assert valid is False
        assert "Unsupported platform" in msg


def test_blocked_private_and_local_ips():
    blocked_urls = [
        "https://localhost/video",
        "https://127.0.0.1/video",
        "https://10.0.0.1/video",
        "https://192.168.1.1/video",
        "https://169.254.169.254/latest/meta-data",
        "https://[::1]/video",
    ]
    for url in blocked_urls:
        valid, msg = validate_url(url)
        assert valid is False


def test_custom_ports_blocked():
    valid, msg = validate_url("https://www.youtube.com:8080/watch?v=123")
    assert valid is False
    assert "Non-standard network ports" in msg


def test_filename_sanitization():
    assert sanitize_filename("Regular Title", "mp4") == "Regular Title.mp4"
    assert sanitize_filename("Title / With: Invalid? *Chars* <And> | More", "mp4") == "Title With Invalid Chars And More.mp4"
    assert sanitize_filename("   ...Leading and Trailing Spaces...   ", "mp3") == "Leading and Trailing Spaces.mp3"
    assert sanitize_filename("", "mp4") == "video.mp4"


def test_format_helpers():
    assert format_duration(45) == "0:45"
    assert format_duration(125) == "2:05"
    assert format_duration(3665) == "1:01:05"
    assert format_bytes(1024) == "1.0 KB"
    assert format_bytes(1048576) == "1.0 MB"
