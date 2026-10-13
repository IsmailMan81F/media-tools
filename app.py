import os
import re
import time
import json
import uuid
import shutil
import socket
import tempfile
import threading
import ipaddress
import subprocess
import urllib.parse
from werkzeug.utils import secure_filename
from flask import Flask, request, jsonify, send_file, Response
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import yt_dlp

app = Flask(__name__, static_folder="static", static_url_path="/static")

# Environment configuration
MAX_DURATION_SECONDS = int(os.environ.get("MAX_DURATION_SECONDS", 3600))
MAX_FILESIZE_MB = int(os.environ.get("MAX_FILESIZE_MB", 1500))
MAX_CONCURRENT_JOBS = int(os.environ.get("MAX_CONCURRENT_JOBS", 3))
JOB_TTL_SECONDS = int(os.environ.get("JOB_TTL_SECONDS", 900))  # 15 minutes TTL
PROXY_URL = os.environ.get("PROXY_URL")
COOKIE_FILE = os.environ.get("COOKIE_FILE")

# Temporary downloads storage
BASE_DOWNLOAD_DIR = os.path.join(tempfile.gettempdir(), "clip_saver_downloads")
os.makedirs(BASE_DOWNLOAD_DIR, exist_ok=True)

# Auto-detect ffmpeg on host or winget if not in standard PATH
if "ffmpeg" not in os.environ.get("PATH", "").lower():
    possible_dirs = [
        r"C:\Users\Ismail\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin",
        os.environ.get("FFMPEG_LOCATION", "")
    ]
    for p in possible_dirs:
        if p and os.path.isdir(p):
            os.environ["PATH"] = p + os.pathsep + os.environ.get("PATH", "")
            break

# Rate Limiter setup
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://"
)

# In-memory job registry and lock
jobs = {}
jobs_lock = threading.Lock()

# In-memory registry for uploaded media and cropped outputs
crop_media = {}
crop_results = {}
crop_lock = threading.Lock()
ALLOWED_UPLOAD_EXTS = {
    "mp4", "webm", "mov", "m4v", "mkv", "avi",
    "mp3", "wav", "m4a", "aac", "ogg", "flac"
}

ALLOWED_DOMAINS = {
    "youtube.com",
    "youtu.be",
    "tiktok.com",
    "instagram.com",
    "facebook.com",
    "fb.watch",
    "x.com",
    "twitter.com"
}


def validate_url(raw_url: str):
    """
    Validates URL safety, scheme, domain whitelist, and guards against SSRF.
    """
    if not raw_url or not isinstance(raw_url, str):
        return False, "A video link is required."

    url = raw_url.strip()
    if len(url) > 2048:
        return False, "Link exceeds the maximum permitted length."

    try:
        parsed = urllib.parse.urlsplit(url)
    except Exception:
        return False, "Malformed link format."

    if parsed.scheme.lower() != "https":
        return False, "Only secure HTTPS links are supported."

    if not parsed.hostname:
        return False, "Invalid host address."

    host = parsed.hostname.lower().rstrip(".")

    # Reject non-standard ports
    if parsed.port and parsed.port != 443:
        return False, "Non-standard network ports are not permitted."

    # Verify domain against whitelist
    is_allowed = host in ALLOWED_DOMAINS or any(host.endswith("." + d) for d in ALLOWED_DOMAINS)
    if not is_allowed:
        return False, "Unsupported platform. Supported platforms: YouTube, TikTok, Instagram, Facebook, and X."

    # SSRF guard: resolve DNS and ensure not private, loopback, or reserved
    try:
        addr_info = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
        if not addr_info:
            return False, "Unable to resolve target host."
        for *_, sockaddr in addr_info:
            ip_str = sockaddr[0]
            ip = ipaddress.ip_address(ip_str)
            if (ip.is_private or ip.is_loopback or ip.is_link_local
                    or ip.is_multicast or ip.is_reserved or ip.is_unspecified):
                return False, "Access to private or restricted network addresses is prohibited."
    except socket.gaierror:
        return False, "Unable to connect to the target host. Verify the address and try again."
    except Exception:
        return False, "Network validation failed for target address."

    return True, url


def sanitize_filename(title: str, ext: str) -> str:
    """
    Creates a clean, safe filename from the video title.
    """
    if not title:
        title = "video"
    # Remove filesystem prohibited characters and controls
    clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]', ' ', title)
    clean = re.sub(r'\s+', ' ', clean).strip()
    clean = clean.strip(".- ")
    if not clean:
        clean = "video"
    if len(clean) > 100:
        clean = clean[:100].strip()
    clean_ext = ext.lstrip(".").lower()
    return f"{clean}.{clean_ext}"


def format_bytes(size: int | float | None) -> str | None:
    if not size or size <= 0:
        return None
    size = float(size)
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024.0:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024.0
    return f"{size:.1f} TB"


def format_duration(seconds: int | float | None) -> str:
    if not seconds:
        return "0:00"
    sec = int(seconds)
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def extract_video_qualities(info: dict):
    formats = info.get("formats", [])
    duration = info.get("duration") or 0
    video_formats = [f for f in formats if f.get("vcodec") != "none" and f.get("height")]
    audio_formats = [f for f in formats if f.get("acodec") != "none" and f.get("vcodec") == "none"]

    best_audio_size = 0
    if audio_formats:
        best_audio = max(audio_formats, key=lambda f: f.get("abr") or f.get("tbr") or 0)
        best_audio_size = best_audio.get("filesize") or best_audio.get("filesize_approx") or 0
        if not best_audio_size and duration and (best_audio.get("abr") or 128):
            best_audio_size = int((best_audio.get("abr") or 128) * 1000 * duration / 8)

    unique_heights = sorted({f.get("height") for f in video_formats}, reverse=True)
    standard_targets = [
        (2160, "2160p (4K)"),
        (1440, "1440p (2K)"),
        (1080, "1080p"),
        (720, "720p"),
        (480, "480p"),
        (360, "360p"),
    ]

    qualities = []
    if unique_heights:
        max_h = max(unique_heights)
        for h_target, label in standard_targets:
            if max_h >= h_target:
                candidates = [f for f in video_formats if f.get("height") <= h_target]
                approx_size_str = None
                if candidates:
                    best_cand = max(candidates, key=lambda f: f.get("height"))
                    v_size = best_cand.get("filesize") or best_cand.get("filesize_approx") or 0
                    if not v_size and duration and (best_cand.get("vbr") or best_cand.get("tbr")):
                        v_size = int((best_cand.get("vbr") or best_cand.get("tbr")) * 1000 * duration / 8)
                    total_size = v_size + (best_audio_size if best_cand.get("acodec") == "none" else 0)
                    approx_size_str = format_bytes(total_size)
                qualities.append({
                    "id": str(h_target),
                    "label": label,
                    "height": h_target,
                    "approx_size": approx_size_str
                })

        # Fallback if video max resolution is lower than 360p (e.g. 240p)
        if not qualities:
            qualities.append({
                "id": str(max_h),
                "label": f"{max_h}p",
                "height": max_h,
                "approx_size": format_bytes(best_audio_size)
            })

    # Always provide Audio only (MP3)
    qualities.append({
        "id": "audio",
        "label": "Audio only (MP3)",
        "height": 0,
        "approx_size": format_bytes(best_audio_size)
    })

    return qualities


def download_worker(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return

    url = job["url"]
    quality = job["quality"]
    job_dir = job["dir"]
    is_audio = (quality == "audio")

    current_stream_idx = [0]
    total_streams = 1 if is_audio else 2

    def progress_hook(d):
        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes") or 0

            # Enforce max filesize limit
            if downloaded > MAX_FILESIZE_MB * 1024 * 1024:
                raise ValueError(f"Download size exceeded the maximum limit of {MAX_FILESIZE_MB} MB.")

            stream_percent = (downloaded / total * 100.0) if total > 0 else 0.0

            # Scale smooth overall percent across streams
            if is_audio:
                overall_percent = min(stream_percent * 0.90, 90.0)
            else:
                idx = current_stream_idx[0]
                if idx == 0:
                    overall_percent = min(stream_percent * 0.45, 45.0)
                else:
                    overall_percent = min(45.0 + (stream_percent * 0.45), 90.0)

            with jobs_lock:
                if job_id in jobs:
                    jobs[job_id]["state"] = "downloading"
                    jobs[job_id]["percent"] = round(overall_percent, 1)
                    jobs[job_id]["message"] = f"Downloading stream... {int(overall_percent)}%"

        elif status == "finished":
            current_stream_idx[0] += 1
            with jobs_lock:
                if job_id in jobs:
                    if current_stream_idx[0] >= total_streams:
                        jobs[job_id]["state"] = "merging"
                        jobs[job_id]["percent"] = 92.0
                        jobs[job_id]["message"] = "Merging streams with ffmpeg..."

    def postprocessor_hook(d):
        status = d.get("status")
        with jobs_lock:
            if job_id in jobs:
                if status == "started":
                    jobs[job_id]["state"] = "merging"
                    jobs[job_id]["percent"] = 95.0
                    jobs[job_id]["message"] = "Processing audio and video..."
                elif status == "finished":
                    jobs[job_id]["percent"] = 98.0
                    jobs[job_id]["message"] = "Finalizing output file..."

    try:
        out_template = os.path.join(job_dir, "%(title).80s.%(ext)s")
        ydl_opts = {
            "outtmpl": out_template,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "progress_hooks": [progress_hook],
            "postprocessor_hooks": [postprocessor_hook],
            "max_filesize": MAX_FILESIZE_MB * 1024 * 1024,
        }
        if PROXY_URL:
            ydl_opts["proxy"] = PROXY_URL
        if COOKIE_FILE and os.path.isfile(COOKIE_FILE):
            ydl_opts["cookiefile"] = COOKIE_FILE

        if is_audio:
            ydl_opts["format"] = "bestaudio/best"
            ydl_opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]
        else:
            try:
                h_val = int(quality)
                ydl_opts["format"] = f"bestvideo[height<={h_val}]+bestaudio/best[height<={h_val}]/bestvideo+bestaudio/best"
            except ValueError:
                ydl_opts["format"] = "bestvideo+bestaudio/best"
            ydl_opts["merge_output_format"] = "mp4"

        with jobs_lock:
            if job_id in jobs:
                jobs[job_id]["state"] = "downloading"
                jobs[job_id]["percent"] = 5.0
                jobs[job_id]["message"] = "Fetching video streams..."

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            extracted_info = ydl.extract_info(url, download=True)
            video_title = extracted_info.get("title") or "video"

        # Locate prepared file in job directory
        candidates = [
            f for f in os.listdir(job_dir)
            if not f.endswith(".part") and not f.endswith(".ytdl") and not f.endswith(".temp")
        ]

        if not candidates:
            raise RuntimeError("Prepared media file not found on disk.")

        # Pick the largest file or the target extension
        target_ext = "mp3" if is_audio else "mp4"
        matched = [f for f in candidates if f.lower().endswith("." + target_ext)]
        chosen_file = matched[0] if matched else max(candidates, key=lambda f: os.path.getsize(os.path.join(job_dir, f)))
        full_path = os.path.join(job_dir, chosen_file)

        ext = chosen_file.rsplit(".", 1)[-1] if "." in chosen_file else target_ext
        clean_name = sanitize_filename(video_title, ext)

        with jobs_lock:
            if job_id in jobs:
                jobs[job_id]["state"] = "ready"
                jobs[job_id]["percent"] = 100.0
                jobs[job_id]["message"] = "Ready for download"
                jobs[job_id]["filepath"] = full_path
                jobs[job_id]["filename"] = clean_name
                jobs[job_id]["title"] = video_title

    except Exception as err:
        error_msg = str(err)
        # Simplify user-facing error message
        if "Unsupported URL" in error_msg:
            clean_error = "The provided URL is not supported."
        elif "Private video" in error_msg or "Sign in" in error_msg:
            clean_error = "This video is private or requires authentication."
        elif "Video unavailable" in error_msg:
            clean_error = "This video is unavailable or has been removed."
        elif "max_filesize" in error_msg or "maximum limit" in error_msg:
            clean_error = f"The video file size exceeds the server limit of {MAX_FILESIZE_MB} MB."
        else:
            clean_error = "An error occurred while preparing the download. Please try again."

        with jobs_lock:
            if job_id in jobs:
                jobs[job_id]["state"] = "error"
                jobs[job_id]["percent"] = 0.0
                jobs[job_id]["message"] = clean_error
                jobs[job_id]["error"] = clean_error


def cleanup_daemon():
    """
    Background worker cleaning up stale job directories after TTL.
    """
    while True:
        time.sleep(60)
        now = time.time()
        to_delete = []
        with jobs_lock:
            for j_id, j_data in list(jobs.items()):
                if now - j_data.get("created_at", now) > JOB_TTL_SECONDS:
                    to_delete.append(j_id)

        # Cleanup downloader jobs
        for j_id in to_delete:
            with jobs_lock:
                j_data = jobs.pop(j_id, None)
            if j_data and j_data.get("dir") and os.path.isdir(j_data["dir"]):
                try:
                    shutil.rmtree(j_data["dir"], ignore_errors=True)
                except Exception:
                    pass

        # Cleanup cropper uploads and results
        crop_to_delete = []
        with crop_lock:
            for c_id, c_data in list(crop_media.items()):
                if now - c_data.get("created_at", now) > JOB_TTL_SECONDS:
                    crop_to_delete.append(c_id)

        for c_id in crop_to_delete:
            with crop_lock:
                c_data = crop_media.pop(c_id, None)
            if c_data and c_data.get("dir") and os.path.isdir(c_data["dir"]):
                try:
                    shutil.rmtree(c_data["dir"], ignore_errors=True)
                except Exception:
                    pass


# Start the cleanup thread as daemon
cleanup_thread = threading.Thread(target=cleanup_daemon, daemon=True)
cleanup_thread.start()


# ---------------- API ENDPOINTS ----------------

@app.route("/")
def index():
    return app.send_static_file("index.html")


@app.route("/health")
def health():
    return jsonify({"status": "healthy"}), 200


@app.route("/api/info", methods=["POST"])
@limiter.limit("10 per minute")
def get_info():
    data = request.get_json(silent=True) or {}
    raw_url = data.get("url")

    valid, result = validate_url(raw_url)
    if not valid:
        return jsonify({"error": result}), 400

    url = result
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }
    if PROXY_URL:
        ydl_opts["proxy"] = PROXY_URL
    if COOKIE_FILE and os.path.isfile(COOKIE_FILE):
        ydl_opts["cookiefile"] = COOKIE_FILE

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return jsonify({"error": "Unable to extract video metadata."}), 400

            duration = info.get("duration") or 0
            if duration > MAX_DURATION_SECONDS:
                mins = MAX_DURATION_SECONDS // 60
                return jsonify({
                    "error": f"The video duration exceeds the maximum limit of {mins} minutes."
                }), 400

            title = info.get("title") or "Untitled Video"
            uploader = (info.get("uploader") or info.get("channel")
                        or info.get("uploader_id") or info.get("creator") or "Unknown creator")
            thumbnail = info.get("thumbnail") or ""
            qualities = extract_video_qualities(info)

            return jsonify({
                "title": title,
                "uploader": uploader,
                "duration": duration,
                "duration_formatted": format_duration(duration),
                "thumbnail": thumbnail,
                "qualities": qualities,
            })

    except Exception as err:
        err_str = str(err)
        if "Private video" in err_str or "Sign in" in err_str:
            return jsonify({"error": "This video is private or requires authentication."}), 400
        if "Video unavailable" in err_str:
            return jsonify({"error": "This video is unavailable or has been removed."}), 400
        return jsonify({"error": "Unable to retrieve video information. Please verify the URL."}), 400


@app.route("/api/prepare", methods=["POST"])
@limiter.limit("10 per minute")
def prepare_download():
    data = request.get_json(silent=True) or {}
    raw_url = data.get("url")
    quality = str(data.get("quality", "1080")).strip()

    valid, result = validate_url(raw_url)
    if not valid:
        return jsonify({"error": result}), 400

    url = result

    # Check concurrent active jobs
    with jobs_lock:
        active_count = sum(
            1 for j in jobs.values()
            if j.get("state") in ("queued", "downloading", "merging")
        )
        if active_count >= MAX_CONCURRENT_JOBS:
            return jsonify({
                "error": f"The server is currently busy processing {MAX_CONCURRENT_JOBS} downloads. Please wait a moment and try again."
            }), 429

        job_id = str(uuid.uuid4())
        job_dir = os.path.join(BASE_DOWNLOAD_DIR, job_id)
        os.makedirs(job_dir, exist_ok=True)

        jobs[job_id] = {
            "id": job_id,
            "url": url,
            "quality": quality,
            "state": "queued",
            "percent": 0.0,
            "message": "Preparing download...",
            "created_at": time.time(),
            "dir": job_dir,
            "filepath": None,
            "filename": None,
            "title": None,
            "error": None,
        }

    # Start background processing thread
    thread = threading.Thread(target=download_worker, args=(job_id,), daemon=True)
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/api/progress/<job_id>", methods=["GET"])
def get_progress(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return jsonify({"error": "Download session expired or not found."}), 404

        return jsonify({
            "state": job["state"],
            "percent": job["percent"],
            "message": job["message"],
        })


@app.route("/api/file/<job_id>", methods=["GET"])
def get_file(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job or job.get("state") != "ready":
            return jsonify({"error": "File is not ready or has expired."}), 404

        filepath = job.get("filepath")
        filename = job.get("filename") or "download.mp4"
        job_dir = job.get("dir")

    if not filepath or not os.path.isfile(filepath):
        return jsonify({"error": "Requested file could not be located on the server."}), 404

    # Stream file to client and delete temp directory upon completion
    def cleanup():
        with jobs_lock:
            jobs.pop(job_id, None)
        if job_dir and os.path.isdir(job_dir):
            try:
                shutil.rmtree(job_dir, ignore_errors=True)
            except Exception:
                pass

    response = send_file(
        filepath,
        as_attachment=True,
        download_name=filename,
        mimetype="application/octet-stream"
    )
    response.call_on_close(cleanup)
    return response


# ---------------- MEDIA CROPPER ENDPOINTS ----------------

def get_media_mimetype(ext: str) -> str:
    ext = ext.lower().lstrip(".")
    mimes = {
        "mp4": "video/mp4",
        "webm": "video/webm",
        "mov": "video/quicktime",
        "m4v": "video/x-m4v",
        "mkv": "video/x-matroska",
        "avi": "video/x-msvideo",
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "m4a": "audio/mp4",
        "aac": "audio/aac",
        "ogg": "audio/ogg",
        "flac": "audio/flac",
    }
    return mimes.get(ext, "application/octet-stream")


def probe_media(filepath: str):
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration,size:stream=codec_type,width,height",
        "-of", "json", filepath
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise ValueError("Unable to read media properties from file.")

    data = json.loads(res.stdout or "{}")
    duration = float(data.get("format", {}).get("duration", 0) or 0)
    streams = data.get("streams", [])
    is_video = any(s.get("codec_type") == "video" for s in streams)
    width = next((s.get("width") for s in streams if s.get("width")), None)
    height = next((s.get("height") for s in streams if s.get("height")), None)

    return {
        "duration": duration,
        "is_video": is_video,
        "width": width,
        "height": height
    }


@app.route("/api/crop/upload", methods=["POST"])
@limiter.limit("20 per minute")
def crop_upload():
    if "file" not in request.files:
        return jsonify({"error": "No media file provided."}), 400

    uploaded = request.files["file"]
    if not uploaded.filename:
        return jsonify({"error": "Empty filename."}), 400

    filename = secure_filename(uploaded.filename)
    if not filename or "." not in filename:
        return jsonify({"error": "Invalid file name or missing extension."}), 400

    ext = filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_UPLOAD_EXTS:
        return jsonify({
            "error": f"Unsupported format. Allowed: {', '.join(sorted(ALLOWED_UPLOAD_EXTS))}"
        }), 400

    file_id = str(uuid.uuid4())
    crop_dir = os.path.join(BASE_DOWNLOAD_DIR, f"crop_{file_id}")
    os.makedirs(crop_dir, exist_ok=True)

    dest_path = os.path.join(crop_dir, f"input.{ext}")
    uploaded.save(dest_path)

    try:
        meta = probe_media(dest_path)
    except Exception as err:
        shutil.rmtree(crop_dir, ignore_errors=True)
        return jsonify({"error": "The uploaded file could not be decoded as valid audio or video."}), 400

    duration = meta["duration"]
    if duration <= 0:
        shutil.rmtree(crop_dir, ignore_errors=True)
        return jsonify({"error": "Media duration is invalid or zero."}), 400

    with crop_lock:
        crop_media[file_id] = {
            "id": file_id,
            "filename": filename,
            "ext": ext,
            "dir": crop_dir,
            "filepath": dest_path,
            "duration": duration,
            "is_video": meta["is_video"],
            "width": meta["width"],
            "height": meta["height"],
            "created_at": time.time(),
        }

    return jsonify({
        "file_id": file_id,
        "filename": filename,
        "duration": duration,
        "duration_formatted": format_duration(duration),
        "is_video": meta["is_video"],
        "preview_url": f"/api/crop/preview/{file_id}",
    })


@app.route("/api/crop/preview/<file_id>", methods=["GET"])
def crop_preview(file_id):
    with crop_lock:
        item = crop_media.get(file_id)

    if not item or not os.path.isfile(item.get("filepath", "")):
        return jsonify({"error": "Media preview not found or expired."}), 404

    mimetype = get_media_mimetype(item["ext"])
    return send_file(item["filepath"], mimetype=mimetype, conditional=True)


@app.route("/api/crop/process", methods=["POST"])
@limiter.limit("15 per minute")
def crop_process():
    data = request.get_json(silent=True) or {}
    file_id = str(data.get("file_id", "")).strip()
    try:
        start_time = max(float(data.get("start_time", 0)), 0.0)
        end_time = float(data.get("end_time", 0))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid start or end timestamp."}), 400

    with crop_lock:
        item = crop_media.get(file_id)

    if not item or not os.path.isfile(item.get("filepath", "")):
        return jsonify({"error": "Original media session expired or not found."}), 404

    duration = item["duration"]
    if end_time <= start_time:
        return jsonify({"error": "End time must be greater than start time."}), 400
    if start_time >= duration:
        return jsonify({"error": "Start time exceeds total media duration."}), 400

    # Clamp end time to actual duration
    end_time = min(end_time, duration)
    clip_duration = end_time - start_time

    crop_dir = item["dir"]
    ext = item["ext"]
    crop_id = str(uuid.uuid4())
    output_filename = f"cropped_{crop_id}.{ext}"
    output_path = os.path.join(crop_dir, output_filename)

    # Step 1: Attempt fast stream-copy
    cmd_copy = [
        "ffmpeg", "-y",
        "-ss", f"{start_time:.3f}",
        "-t", f"{clip_duration:.3f}",
        "-i", item["filepath"],
        "-c", "copy",
        output_path
    ]
    res = subprocess.run(cmd_copy, capture_output=True)

    # Step 2: Fallback to re-encode if stream copy fails
    if res.returncode != 0 or not os.path.isfile(output_path) or os.path.getsize(output_path) < 100:
        if item["is_video"]:
            cmd_reencode = [
                "ffmpeg", "-y",
                "-ss", f"{start_time:.3f}",
                "-t", f"{clip_duration:.3f}",
                "-i", item["filepath"],
                "-c:v", "libx264", "-preset", "fast",
                "-c:a", "aac",
                output_path
            ]
        else:
            cmd_reencode = [
                "ffmpeg", "-y",
                "-ss", f"{start_time:.3f}",
                "-t", f"{clip_duration:.3f}",
                "-i", item["filepath"],
                output_path
            ]
        res_reencode = subprocess.run(cmd_reencode, capture_output=True)
        if res_reencode.returncode != 0 or not os.path.isfile(output_path):
            return jsonify({"error": "Failed to process media crop operation."}), 500

    clean_export_name = sanitize_filename("cropped_" + item["filename"].rsplit(".", 1)[0], ext)

    with crop_lock:
        crop_results[crop_id] = {
            "crop_id": crop_id,
            "file_id": file_id,
            "filepath": output_path,
            "filename": clean_export_name,
            "dir": crop_dir,
            "created_at": time.time(),
        }

    return jsonify({
        "crop_id": crop_id,
        "filename": clean_export_name,
        "download_url": f"/api/crop/download/{crop_id}"
    })


@app.route("/api/crop/download/<crop_id>", methods=["GET"])
def crop_download(crop_id):
    with crop_lock:
        item = crop_results.get(crop_id)

    if not item or not os.path.isfile(item.get("filepath", "")):
        return jsonify({"error": "Cropped file expired or not found."}), 404

    filepath = item["filepath"]
    filename = item.get("filename") or "cropped_media.mp4"
    crop_dir = item.get("dir")

    def cleanup():
        with crop_lock:
            crop_results.pop(crop_id, None)
        if crop_dir and os.path.isdir(crop_dir):
            try:
                shutil.rmtree(crop_dir, ignore_errors=True)
            except Exception:
                pass

    response = send_file(
        filepath,
        as_attachment=True,
        download_name=filename,
        mimetype="application/octet-stream"
    )
    response.call_on_close(cleanup)
    return response


@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({
        "error": "Rate limit exceeded. Please wait a minute before making more requests."
    }), 429


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Endpoint not found."}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "An internal server error occurred."}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
