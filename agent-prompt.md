# Task: Build and deploy "Clip Saver", a video downloader web app

You are a senior full-stack engineer. Build the app described below, test it, and deploy it to a public URL. Do not stop at a local demo. If you need something from me (hosting account, token, platform choice), ask once, clearly, then continue.

## 1. What the app does

A single-page web app where the user:

1. Pastes a video link (short or full-length) from YouTube (videos and Shorts), TikTok, Instagram, Facebook, or X (Twitter).
2. Presses "Check link". The app shows the video's thumbnail, title, uploader, and duration, plus the list of available qualities.
3. Chooses a quality (for example 2160p, 1440p, 1080p, 720p, 480p, 360p, plus "Audio only (MP3)"). Only show qualities that actually exist for that video.
4. Presses "Download". The server prepares the file, the UI shows a real progress bar (percent, and a state label such as Fetching, Merging, Ready), and when ready the browser downloads the file automatically with a clean filename (the video title, sanitized).

## 2. Architecture (a backend is required)

A browser-only HTML file cannot do this: the target sites block cross-origin requests and do not expose direct video URLs. So build:

- **Backend:** Python 3.12, Flask, `yt-dlp` (latest, installed from PyPI), `ffmpeg` (needed to merge separate video and audio streams and to produce MP3). Serve with `gunicorn` (gthread workers, 1 worker, several threads).
- **Frontend:** one static `index.html` with inline CSS and vanilla JS, served by Flask from `/static`. No frameworks, no build step, no CDN links.
- **Endpoints:**
  - `POST /api/info` with `{url}` returns `{title, uploader, duration, thumbnail, qualities: [{id, label, height, approx_size}]}`.
  - `POST /api/prepare` with `{url, quality}` starts a background job and returns `{job_id}`.
  - `GET /api/progress/<job_id>` returns `{state, percent, message}` (states: queued, downloading, merging, ready, error).
  - `GET /api/file/<job_id>` streams the finished file with `Content-Disposition: attachment`, then deletes the temp file and job.
- Use yt-dlp's Python API with `progress_hooks`. Format selector for height H: `bestvideo[height<=H]+bestaudio/best[height<=H]`, merge to mp4. Audio only: extract to mp3.
- Run jobs in background threads. Keep job state in memory. Delete temp files after download and after a 15-minute TTL.

## 3. Safety and abuse limits (required, the app is public)

- Allow only these hosts (including subdomains): youtube.com, youtu.be, tiktok.com, instagram.com, facebook.com, fb.watch, x.com, twitter.com. Reject everything else with a clear message. Validate the URL scheme (https only) to prevent SSRF.
- Per-IP rate limit (for example 10 requests per minute on `/api/info` and `/api/prepare`).
- Environment-configurable caps: `MAX_DURATION_SECONDS` (default 3600), `MAX_FILESIZE_MB` (default 1500), `MAX_CONCURRENT_JOBS` (default 3).
- Never expose stack traces to the client. Return short, human-readable error messages.
- Show this notice in the footer: "Only download videos you own or have permission to save. Respect each platform's terms and the creator's rights."

## 4. Design system (follow exactly)

**Theme:** light. Warm parchment printed artifact: ink on bone paper, with clay as the only chromatic breath. Flat surfaces, generous corner radii, hairline borders, almost no shadow, no gradients, no glow, no 3D.

### Colors

| Name | Value | Role |
|---|---|---|
| Bone Parchment | `#f8f8f6` | Page canvas, nav bar |
| Paper White | `#ffffff` | Elevated card surfaces |
| Soft Stone | `#efeeeb` | Nested surfaces, subtle bands |
| Carbon Ink | `#121212` | Primary text, headings, icons |
| Graphite | `#373734` | Secondary text, button/nav text |
| Ashen | `#7b7974` | Muted helper text, captions |
| Pebble | `#9c9a92` | Tertiary text |
| Mist | `#b7b7b5` | Input borders, dividers |
| Chalk | `#e7e6e1` | Hairline card borders, tints |
| Obsidian | `#000000` | Footer background only |
| Clay | `#d97757` | Decorative accent only (small marks, progress bar fill, a small dot beside the headline). Never a button fill, never a link color |

Do not use blue, green or red anywhere. Errors and success are communicated with the warm-gray palette, an icon, and clear text.

### Typography

- **Display (serif):** the design uses "Anthropic Serif", which is proprietary. Use the substitute **Source Serif 4**, weight 400, sizes 24px and 30px only, line-height 1.2 (30px) and 1.33 (24px). Used only for headlines and card titles.
- **Interface (sans):** the design uses "Anthropic Sans", which is proprietary. Use the substitute **Inter**, weights 400, 500, 600 (use 500 for buttons and labels; never go heavier than 600). Sizes 11px, 12px, 14px, 15px, 16px, 24px. Line-height 1.5.
- Download the font files and self-host them: use the npm packages `@fontsource/source-serif-4` and `@fontsource/inter` (woff2, latin subset) and copy the files into `static/fonts/`. Declare them with `@font-face` and `font-display: swap`. Fallback stacks: serif `ui-serif, Georgia, Cambria, "Times New Roman", serif`; sans `ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`.
- Type scale: caption 11px, body 14px, section/card heading 24px serif, hero heading 30px serif. Hierarchy comes from size and weight contrast, not from bold.

### Spacing, shape, layout

- Base unit 8px. Scale: 8, 16, 24, 32, 40, 64, 80, 96.
- Radius: cards 16px, elevated cards 24px, buttons, inputs and nav 8px.
- Page max-width 1200px, centered. Card padding 32px. Gap between elements inside a component 8 to 12px. Gap between major sections 64 to 80px.
- Shadow: none by default. On hover or for the featured card only: `0 4px 20px rgba(0,0,0,0.04)`.

### Components

- **Primary button (Filled Dark):** background `#121212`, text `#f8f8f6`, radius 8px, padding 8px 20px, 15px Inter weight 500. Hover: background `#373734`. Disabled: background `#b7b7b5`, text `#f8f8f6`. This is the Download button and the Check link button.
- **Secondary / nav button:** transparent, Graphite text, no border, radius 8px, hover to Carbon Ink with 0.2s ease.
- **Input:** Paper White fill, 1px border `#b7b7b5`, radius 8px, 14px Inter. Focus: visible 2px outline in Graphite with 2px offset (keyboard focus must be clearly visible).
- **Main card:** Paper White on Bone Parchment, radius 24px, padding 32px, optional 1px hairline `#e7e6e1`.
- **Nested card (video preview, quality options):** Soft Stone or Paper White, radius 16px, padding 24px, flat.
- **Quality selector:** a group of selectable option tiles (radio semantics, keyboard accessible). Selected tile: 1px solid Carbon Ink border plus a Lucide `check` icon. Unselected: 1px `#e7e6e1` border.
- **Progress bar:** 8px tall, Soft Stone track, Clay fill, radius 8px, with a text label in Ashen 12px beside it. Respect `prefers-reduced-motion`.
- **Status message:** 8px radius, 12px text, warm-gray tinted background with an icon (`circle-alert` for errors, `check` for success).
- **Footer band:** Obsidian background, 64px vertical padding, text and links in Pebble 14px, copyright 12px.
- **Clay accent mark:** a small Clay dot beside the hero headline. This is the only decorative use of Clay besides the progress fill.

### Icons

Do not use emojis anywhere (UI, code comments, README, commit messages). Download real icons: install the npm package `lucide-static` and copy only the SVGs you need into `static/icons/`: `download`, `link`, `clipboard-paste`, `check`, `circle-alert`, `loader-circle`, `film`, `clock`, `user`, `x`. Inline them as SVG (stroke `currentColor`, stroke-width 2) so they inherit Carbon Ink. Icons are mono, never multicolor.

### Page layout (one page)

1. Minimal top nav on Bone Parchment: wordmark "Clip Saver" (Inter 500) on the left, no heavy borders.
2. Hero, centered, 64 to 80px vertical padding: serif 30px headline (for example "Save any video, in the quality you choose"), a 16px Graphite sentence below, and the Clay dot.
3. Main card (24px radius): link input with a "Paste" button (clipboard-paste icon) and the "Check link" button.
4. After a successful check, a nested card shows: thumbnail (16px radius), title, uploader (user icon), duration (clock icon); below it the quality tiles; below that the Download button and progress bar.
5. Empty, loading, and error states are all designed. Errors say what went wrong and how to fix it, with no apology and no vague wording. Button labels keep the same verb through the flow ("Download" produces "Downloaded").
6. Footer band with the usage notice.

### Design rules

- Never use pure black for text; use Carbon Ink `#121212`. Never use pure white for the page background.
- Do not add gradients, heavy shadows, bold weights above 600, sans-serif for large headlines, or any chromatic color other than Clay.
- Fully responsive down to 360px wide. Layout stacks to a single column on mobile; the quality tiles wrap.
- Accessibility: labels on all controls, `aria-live="polite"` on progress and status text, visible keyboard focus, WCAG AA contrast (use Carbon Ink or Graphite for any text that matters; Ashen only for helper text of 12px and larger).

## 5. Project structure

```
clip-saver/
  app.py
  requirements.txt        # flask, gunicorn, yt-dlp, flask-limiter
  Dockerfile              # python:3.12-slim, apt install ffmpeg, pip install, gunicorn CMD
  .dockerignore
  .env.example            # MAX_DURATION_SECONDS, MAX_FILESIZE_MB, MAX_CONCURRENT_JOBS
  README.md               # run locally, deploy, update yt-dlp
  static/
    index.html
    fonts/
    icons/
```

## 6. Testing (do this before deploying)

- Unit-check URL validation (allowed hosts accepted; other hosts, `http://`, `file://`, and internal IPs rejected).
- Run the app locally with Docker. Test one short YouTube video end to end: check link, pick a quality, download, confirm the file plays and the filename is clean. Test audio only. Test an invalid link and a blocked host and confirm the error messages.
- Check the UI at 360px, 768px, and 1280px widths. Confirm fonts load from `static/fonts` (no external requests) and no emojis exist anywhere.

## 7. Deployment

- Deploy the Docker image to a host that runs long-lived containers and allows ffmpeg (Render, Railway, or Fly.io; pick one, or ask me which I prefer if you have credentials for several). Do not use serverless platforms (Vercel, Netlify functions): downloads and merging exceed their time and size limits.
- Configure the environment variables from `.env.example`, set the health check to `/`, and return the public HTTPS URL when done.
- Add a note in the README about `yt-dlp` breaking when sites change: redeploy with `pip install -U yt-dlp` regularly (or add a weekly rebuild).
- Known limitation to report honestly in your final message: YouTube, Instagram, and others often block requests from datacenter IP addresses. If downloads fail on the deployed server but work locally, tell me, and propose options (a residential proxy via the `--proxy` option, or cookies exported from my own account with the `cookiefile` option kept in a secret, never committed).

## 8. Definition of done

- A public HTTPS URL where I can paste a link from each supported platform, choose a quality, and download the file.
- The design matches the system above, with self-hosted fonts and real SVG icons, and no emojis.
- A short final report: what was built, the URL, how to redeploy, and any limitations you found.
