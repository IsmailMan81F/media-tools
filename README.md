# Clip Saver

Clip Saver is a clean, reliable web application for saving videos and audio from YouTube (videos and Shorts), TikTok, Instagram, Facebook, and X (Twitter).

The application is built with a lightweight Python/Flask backend utilizing `yt-dlp` and `ffmpeg`, and a frontend crafted in vanilla HTML, CSS, and JavaScript following the Warm Parchment design system.

---

## Features

- **Supported Platforms:** YouTube (Videos and Shorts), TikTok, Instagram Reels, Facebook, and X (Twitter).
- **Quality Selector:** Automatically detects available video resolutions (e.g., 2160p 4K, 1440p 2K, 1080p HD, 720p, 480p, 360p) and MP3 audio extraction.
- **Asynchronous Processing:** Downloads and streams are processed in background threads without blocking client requests.
- **Real-Time Progress:** Polling progress indicator displaying current state (Queued, Downloading, Merging, Ready).
- **Automatic Clean Downloads:** Files are named using the sanitized video title and delivered directly to the client browser.
- **Security and Abuse Protection:**
  - Whitelist domain enforcement with SSRF defense preventing access to private, loopback, or non-standard addresses.
  - Per-IP rate limiting (10 requests per minute on `/api/info` and `/api/prepare`).
  - Configurable duration caps, file size limits, and concurrent job thresholds.
  - Automatic cleanup of temporary files upon download completion and through a 15-minute TTL background daemon.
- **Self-Contained Interface:**
  - Self-hosted fonts (`Inter` and `Source Serif 4`).
  - Monochromatic SVG icons from `lucide-static`.
  - Zero external CDN dependencies.

---

## Local Development Setup

### Prerequisites

- Python 3.12 or newer
- FFmpeg installed and available on system PATH

### Installation

1. Clone or navigate to the repository directory:
   ```bash
   cd video-downloader
   ```

2. Create and activate a Python virtual environment:
   ```bash
   python -m venv venv
   # On Linux/macOS:
   source venv/bin/activate
   # On Windows PowerShell:
   .\venv\Scripts\Activate.ps1
   ```

3. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Run the development server:
   ```bash
   python app.py
   ```

5. Open `http://localhost:5000` in your browser.

---

## Running with Docker

1. Build the Docker container image:
   ```bash
   docker build -t clip-saver .
   ```

2. Run the container:
   ```bash
   docker run -d -p 5000:5000 \
     -e MAX_DURATION_SECONDS=3600 \
     -e MAX_FILESIZE_MB=1500 \
     -e MAX_CONCURRENT_JOBS=3 \
     --name clip-saver-instance clip-saver
   ```

3. Access the service at `http://localhost:5000`.

---

## Deployment Instructions

Clip Saver requires a hosting platform capable of running long-lived container processes and executing FFmpeg (such as Render, Railway, or Fly.io). Serverless runtimes (such as Vercel or AWS Lambda) are unsuitable due to execution timeouts and payload size limits during video download and merge operations.

### Deploying to Render

1. Create a new Web Service on Render connected to this repository (or deploy via Docker).
2. Specify the Runtime as `Docker`.
3. Set the Health Check Path to `/`.
4. Configure Environment Variables:
   - `PORT`: `5000`
   - `MAX_DURATION_SECONDS`: `3600`
   - `MAX_FILESIZE_MB`: `1500`
   - `MAX_CONCURRENT_JOBS`: `3`
   - `JOB_TTL_SECONDS`: `900`
5. Click **Create Web Service**.

### Deploying to Railway

1. Install the Railway CLI or link the repository from GitHub.
2. Deploy the container using Railway:
   ```bash
   railway up
   ```
3. Set the environment variables in the Railway dashboard.
4. Generate a public domain under service settings.

### Deploying to Fly.io

1. Launch a new application:
   ```bash
   fly launch --no-deploy
   ```
2. Deploy the app:
   ```bash
   fly deploy
   ```

---

## Maintenance: Updating yt-dlp

Target platforms (YouTube, Instagram, TikTok) constantly alter their video players, anti-bot mechanisms, and delivery endpoints. To ensure uninterrupted operation:

1. Update `yt-dlp` regularly:
   ```bash
   pip install -U yt-dlp
   ```
2. On container platforms, trigger a weekly rebuild or redeploy so the latest release of `yt-dlp` from PyPI is incorporated into the running image.

---

## Known Platform Limitations & Datacenter IP Blocks

Major video platforms (especially YouTube and Instagram) frequently block or throttle requests originating from commercial datacenter IP ranges (AWS, GCP, DigitalOcean, Render, Fly.io).

If the deployed application encounters `Sign in to confirm you're not a bot` or `HTTP Error 429: Too Many Requests` while local requests succeed:

1. **Residential Proxy:**
   Configure a residential proxy in `yt-dlp` by passing the `--proxy` URL in `app.py` or via an environment variable `PROXY_URL`.
2. **Authenticated Cookies:**
   Export browser cookies from an authenticated session into a Netscape formatted cookie file and point `yt-dlp` to it using the `cookiefile` parameter. Store this file securely as an environment secret and never commit it to source control.

---

## License & Usage Notice

Only download videos you own or have permission to save. Respect each platform's terms of service and creator copyright.
