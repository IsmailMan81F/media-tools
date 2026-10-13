# Clip Saver

Clip Saver is a clean, single-page video and audio downloader web application designed to save media from YouTube (standard videos and Shorts), TikTok, Instagram (Reels), Facebook, and X (formerly Twitter).

The project is built on the Warm Parchment design system: an editorial, print-inspired aesthetic featuring ink on bone paper, restrained typography, and a single chromatic accent of clay orange.

---

## Table of Contents

1. [Overview](#overview)
2. [Key Capabilities](#key-capabilities)
3. [Architecture and How It Works](#architecture-and-how-it-works)
4. [Technology Stack](#technology-stack)
5. [Design System & Interface](#design-system--interface)
6. [Security & Abuse Prevention](#security--abuse-prevention)
7. [Current Hosting Setup](#current-hosting-setup)
8. [Manual Hosting Guide](#manual-hosting-guide)
   - [Method 1: Local or Dedicated Server (Python)](#method-1-local-or-dedicated-server-python)
   - [Method 2: Docker Container](#method-2-docker-container)
   - [Method 3: Cloud Platforms (Render, Railway, Fly.io)](#method-3-cloud-platforms-render-railway-flyio)
   - [Method 4: Exposing with Cloudflare Tunnel](#method-4-exposing-with-cloudflare-tunnel)
9. [Maintenance & Troubleshooting](#maintenance--troubleshooting)

---

## Overview

Modern video streaming platforms restrict cross-origin access and do not expose static file URLs directly in the browser. A browser-only web application cannot download or merge these media streams due to Cross-Origin Resource Sharing (CORS) constraints and separate adaptive bitrate streams (DASH/HLS).

Clip Saver bridges this gap with a dedicated backend service that handles media stream extraction, download orchestration, and format transcoding using `yt-dlp` and `ffmpeg`, while providing a responsive, accessible interface with real-time progress tracking.

---

## Key Capabilities

### 1. Media Downloader
- **Multi-Platform Support:** Handles links from YouTube (standard videos & Shorts), TikTok, Instagram (Reels), Facebook, and X.
- **Pre-Flight Metadata Inspection:** Extracts video title, uploader name, duration, and thumbnail preview without downloading the media payload.
- **Dynamic Quality Filtering:** Detects and displays only the resolutions that actually exist for the requested video (2160p 4K, 1440p 2K, 1080p, 720p, 480p, 360p, 240p).
- **MP3 Audio Extraction:** Dedicated audio extraction option converting the stream to high-quality MP3 format.
- **Asynchronous Background Processing:** Heavy download and transcoding operations run in dedicated background threads.
- **Live Progress Updates:** Real-time polling updates the client with download percentage and processing state.
- **Automated Delivery:** Automatically triggers a browser download with a sanitized, filesystem-safe filename.

### 2. Media Cropper & Trimmer
- **Audio and Video Support:** Upload local media files (MP4, WebM, MOV, MKV, MP3, WAV, M4A, AAC, FLAC up to 500 MB).
- **Embedded Media Preview:** Dedicated video player or audio wave preview with synchronized playback.
- **Interactive Timeline & Boundaries:** Visual track with start and end markers (borns), position playhead, and fine-tuning timestamp controls.
- **Fast Lossless Trimming:** Employs FFmpeg stream-copy with automated fallback to high-quality re-encoding.
- **Range Previewing:** Built-in preview player auditioning the exact selected clip range before export.
- **Instant Export:** Direct download of the cropped media file with automated temporary storage cleanup.

### 3. Application Shell & Navigation
- **Collapsible Desktop Sidebar:** Smooth sliding animation with an icon-only collapsed mode displaying navigation icons with tooltips.
- **Responsive Mobile Drawer:** Top-bar hamburger menu with animated slide-in drawer and overlay backdrop for mobile viewports.

---

## Architecture and How It Works

```
[ User Browser ]
       |
       | 1. POST /api/info { url }
       v
[ Flask Backend ] ---> [ yt-dlp Metadata Extraction ]
       |
       | 2. Returns metadata and available qualities
       v
[ User Selects Quality & Clicks Download ]
       |
       | 3. POST /api/prepare { url, quality }
       v
[ Background Worker Thread ]
       |---> Downloads video stream (yt-dlp)
       |---> Downloads audio stream (yt-dlp)
       |---> Merges streams with FFmpeg to MP4 (or extracts MP3)
       |
       | 4. GET /api/progress/<job_id> (Polled every 750ms)
       v
[ Worker Completes: State = "ready" ]
       |
       | 5. GET /api/file/<job_id> (Automatic download trigger)
       v
[ File Streamed to Browser ]
       |
       +---> Post-response hook deletes temporary disk directory
```

### Format Selection Logic
- **Video:** The backend requests `bestvideo[height<=H]+bestaudio/best[height<=H]`, merged into an MP4 container with FFmpeg.
- **Audio Only:** The backend extracts the highest quality audio stream (`bestaudio/best`) and converts it to MP3 at 192 kbps using the `FFmpegExtractAudio` post-processor.

### Job Lifecycle and Cleanup
1. Each download job receives a unique UUID4 identifier and an isolated directory in the system temp directory (`clip_saver_downloads/<job_id>`).
2. When the user requests `/api/file/<job_id>`, the file is streamed as an attachment.
3. A Flask `response.call_on_close` hook deletes the temporary folder and removes the job entry from memory once the response transmission finishes.
4. If a client disconnects or abandons a download, an internal daemon thread running every 60 seconds purges any job directories older than 15 minutes (`JOB_TTL_SECONDS`).

---

## Technology Stack

### Backend
- **Python 3.12:** Core application runtime.
- **Flask:** Lightweight WSGI framework serving API endpoints and static assets.
- **Gunicorn:** Production WSGI HTTP server using `gthread` workers for high concurrent thread throughput.
- **yt-dlp:** Video format extraction and media retrieval engine.
- **FFmpeg:** Video stream multiplexing, audio stream merging, and audio transcoding.
- **Flask-Limiter:** In-memory rate limiting based on remote client IP addresses.

### Frontend
- **HTML5 & Vanilla JavaScript:** Single-page application with zero external frameworks, libraries, or build steps.
- **Inline CSS:** Complete styling self-contained within `index.html`.
- **Self-Hosted Typography:**
  - `Anthropic Serif` / `Source Serif 4` (Weight 400 for editorial headings).
  - `Anthropic Sans` / `Inter` (Weights 400, 500, 600 for interface text and controls).
- **Lucide Icons:** Monochromatic SVG assets inlined directly (`download`, `link`, `clipboard-paste`, `check`, `circle-alert`, `loader-circle`, `film`, `clock`, `user`, `x`).
- **Zero CDNs:** The page makes zero external script, font, or stylesheet network calls.

---

## Design System & Interface

The user interface follows the Warm Parchment specification:
- **Palette:**
  - Bone Parchment (`#f8f8f6`): Base canvas and navigation background.
  - Paper White (`#ffffff`): Elevated main card surface.
  - Soft Stone (`#efeeeb`): Nested video card and input bands.
  - Carbon Ink (`#121212`): Primary text, headings, and primary button fills.
  - Graphite (`#373734`): Secondary copy and interactive hover states.
  - Ashen (`#7b7974`): Captions, timestamps, and helper text.
  - Pebble (`#9c9a92`): Low-priority footer links and labels.
  - Mist (`#b7b7b5`): Input borders and hairline dividers.
  - Chalk (`#e7e6e1`): Card borders and unselected tile outlines.
  - Obsidian (`#000000`): Footer surface only.
  - Clay (`#d97757`): The single decorative accent (progress bar fill, brand dot mark).
- **No Chromatic Colors:** No blue, green, or red colors are used. Success and error states are represented through monochromatic icons and warm-gray contextual badges.
- **No Emojis:** The interface relies solely on SVG iconography.
- **Accessibility:** Full keyboard navigation on quality tiles (radio semantics), explicit visible focus rings, and `aria-live="polite"` regions for progress notifications.

---

## Security & Abuse Prevention

1. **Strict Whitelist Validation:** Only the following hosts and their subdomains are accepted:
   - `youtube.com`
   - `youtu.be`
   - `tiktok.com`
   - `instagram.com`
   - `facebook.com`
   - `fb.watch`
   - `x.com`
   - `twitter.com`
2. **SSRF (Server-Side Request Forgery) Defense:**
   - URLs must strictly use the `https` scheme.
   - Non-standard network ports are rejected.
   - Hostnames are resolved through DNS pre-flight checks. Any IP address belonging to private, loopback, link-local, multicast, or reserved ranges (such as `127.0.0.1`, `10.0.0.0/8`, `192.168.0.0/16`, `169.254.169.254`, `::1`) is immediately blocked.
3. **Rate Limiting:**
   - 10 requests per minute per IP address on `/api/info` and `/api/prepare`.
4. **Configurable Server Caps:**
   - `MAX_DURATION_SECONDS`: Prevents extraction of excessively long streams (default: 3600 seconds / 1 hour).
   - `MAX_FILESIZE_MB`: Enforces an upper limit during stream download (default: 1500 MB).
   - `MAX_CONCURRENT_JOBS`: Rejects additional downloads with HTTP 429 when the worker queue reaches capacity (default: 3 jobs).
5. **Information Leakage Prevention:**
   - Stack traces and internal exceptions are suppressed from client responses.

---

## Current Hosting Setup

The application is currently running with the following active architecture:

1. **Local Server Process:**
   - Running locally on `http://127.0.0.1:5000` via the virtual environment.
2. **Public Edge Tunnel (Cloudflare Tunnel):**
   - Exposed to the internet via `cloudflared` over an encrypted QUIC tunnel.
   - **Active Public URL:** [https://jets-uri-reggae-diversity.trycloudflare.com](https://jets-uri-reggae-diversity.trycloudflare.com)
   - No public router port forwarding or firewall adjustments were required.

---

## Manual Hosting Guide

### Method 1: Local or Dedicated Server (Python)

#### 1. System Requirements
- Python 3.12 or newer.
- FFmpeg installed and available on system PATH.

#### 2. Setup Steps

```bash
# 1. Clone or navigate to the project directory
cd video-downloader

# 2. Create and activate a virtual environment
python -m venv venv

# On Linux/macOS:
source venv/bin/activate

# On Windows PowerShell:
.\venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables (optional)
cp .env.example .env

# 5. Run the application
python app.py
```

On Linux or macOS in production, run with Gunicorn:
```bash
gunicorn -w 1 -k gthread --threads 4 -b 0.0.0.0:5000 app:app
```

---

### Method 2: Docker Container

The repository includes a multi-stage `Dockerfile` based on `python:3.12-slim` with FFmpeg installed.

#### 1. Build the Docker Image
```bash
docker build -t clip-saver .
```

#### 2. Run the Container
```bash
docker run -d \
  --name clip-saver-app \
  -p 5000:5000 \
  -e MAX_DURATION_SECONDS=3600 \
  -e MAX_FILESIZE_MB=1500 \
  -e MAX_CONCURRENT_JOBS=3 \
  clip-saver
```

Access the app at `http://localhost:5000`.

---

### Method 3: Cloud Platforms (Render, Railway, Fly.io)

Do **not** deploy this project to serverless functions (such as Vercel Functions or Netlify Functions) because video merging exceeds serverless duration and disk size constraints. Use a container runtime:

#### Deploying to Render

Render supports this application natively via Docker and provides full FFmpeg execution.

##### Option A: 1-Click Blueprint (Recommended)
This repository includes a pre-configured `render.yaml` Blueprint specification.
1. Push this repository to GitHub or GitLab.
2. In the [Render Dashboard](https://dashboard.render.com), click **New + > Blueprint**.
3. Select this repository.
4. Render automatically reads `render.yaml`, configures the Docker runtime, sets `/health` as the health check, and provisions the service.
5. Click **Apply**.

##### Option B: Manual Web Service
1. In the [Render Dashboard](https://dashboard.render.com), click **New + > Web Service**.
2. Connect your Git repository.
3. Name your service (e.g., `clip-saver`).
4. Set **Runtime** to `Docker`.
5. Set **Health Check Path** to `/health` (or `/`).
6. Under **Environment Variables**, configure:
   - `MAX_DURATION_SECONDS`: `3600`
   - `MAX_FILESIZE_MB`: `1500`
   - `MAX_CONCURRENT_JOBS`: `3`
   - `JOB_TTL_SECONDS`: `900`
7. Click **Create Web Service**. Render will build the container, verify the health check, and assign a public `https://<service-name>.onrender.com` URL.

#### Deploying to Railway
1. Install the Railway CLI: `npm install -g @railway/cli` or link through GitHub.
2. Run in the project directory:
   ```bash
   railway init
   railway up
   ```
3. In the Railway dashboard under service settings, click **Generate Domain** to get a public HTTPS URL.

#### Deploying to Fly.io
1. Install the Fly CLI: `flyctl`.
2. Launch and deploy:
   ```bash
   fly launch --no-deploy
   fly deploy
   ```

---

### Method 4: Exposing with Cloudflare Tunnel

To make a local or self-hosted instance accessible over a public HTTPS URL:

1. Download and install `cloudflared`:
   - Windows: `winget install Cloudflare.cloudflared`
   - Linux: `sudo apt install cloudflared` or download from Cloudflare releases.
2. Start the Clip Saver server:
   ```bash
   python app.py
   ```
3. In a separate terminal, launch the quick tunnel:
   ```bash
   cloudflared tunnel --url http://127.0.0.1:5000
   ```
4. Copy the resulting `https://*.trycloudflare.com` URL provided in the console output.

---

## Maintenance & Troubleshooting

### Regular `yt-dlp` Updates
Video platforms frequently update their web players and video streaming signatures. When an extraction error begins occurring across supported platforms:
```bash
pip install -U yt-dlp
```
For Docker deployments, periodically rebuild the container image to retrieve the latest version from PyPI.

### Handling Datacenter IP Blocks
Target platforms (particularly YouTube and Instagram) frequently block or serve anti-bot challenges to requests originating from cloud hosting IP ranges (AWS, DigitalOcean, Render, GCP).

If local downloads succeed but the deployed cloud service returns `Sign in to confirm you're not a bot`:
1. **Residential Proxy:**
   Set the `PROXY_URL` environment variable:
   ```bash
   export PROXY_URL="http://user:password@proxy-service.com:8080"
   ```
2. **Authenticated Session Cookies:**
   Export cookies from an authenticated browser session into a Netscape formatted text file and specify the file path in `COOKIE_FILE`:
   ```bash
   export COOKIE_FILE="/path/to/cookies.txt"
   ```
   *Never commit cookie files to source control.*

---

## Project Structure

```
video-downloader/
├── app.py                 # Core Flask application and download worker
├── requirements.txt       # Python package dependencies
├── Dockerfile             # Production container definition
├── .dockerignore          # Container build exclusion rules
├── .env.example           # Configuration template
├── README.md              # Project documentation
├── test_validation.py     # Unit tests for URL and input validation
├── test_app_e2e.py        # End-to-end integration test suite
└── static/
    ├── index.html         # Single-page user interface
    ├── fonts/             # Self-hosted Source Serif 4 and Inter fonts
    └── icons/             # Monochromatic Lucide SVG icons
```

---

## Usage Notice

Only download videos you own or have permission to save. Respect each platform's terms of service and creator copyright.
