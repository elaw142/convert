# convert

A minimal self-hosted universal file converter. Drop a file, pick a target
format, download the result. The friendly face over `ffmpeg`, `Pillow`, and
`poppler`.

Part of the same family as [grab](../grab) and [send](../send): shared terminal
design language, its own signature colour (amber / "transmutation lab").

## Features

- Drag-and-drop a file → only the formats it can become are offered
- Converted files auto-delete after a TTL (default 10 min)
- Clean async convert → poll → download flow with an in→out size delta

## Supported conversions

| Category | Inputs | Targets | Engine |
| --- | --- | --- | --- |
| Image | png, jpg, webp, gif, bmp, tiff | png, jpg, webp, gif, bmp, tiff, **pdf** | Pillow |
| Audio | mp3, wav, flac, m4a, ogg, aac | mp3, wav, flac, m4a, ogg, aac | ffmpeg |
| Video | mp4, mov, webm, mkv, avi, flv, m4v | mp4, webm, mkv, gif, + extract mp3/m4a/wav | ffmpeg |
| PDF | pdf | png, jpg (multi-page → zip) | poppler |

## Stack

- **Backend**: Python / Flask
- **Engines**: Pillow (images), ffmpeg (audio/video), poppler-utils (pdf→image)
- **Container**: Docker

## Setup

### Running

```bash
git clone https://github.com/elaw142/convert.git
cd convert
# Optional: copy .env.example to .env and tune the limits
docker compose up -d --build
```

The app runs on port `5011` by default.

### Caddy (reverse proxy)

```
convert.yourdomain.com {
    reverse_proxy convert:5011
}
```

### Local (no Docker)

Needs `ffmpeg` and `poppler-utils` on your PATH for audio/video/pdf; image
conversion works with just Pillow.

```bash
pip install -r requirements.txt
python app.py
```

## Configuration

| Variable               | Default | Meaning                                   |
| ---------------------- | ------- | ----------------------------------------- |
| `CONVERT_MAX_FILE_MB`  | `1024`  | Max size of a single upload               |
| `CONVERT_TTL`          | `600`   | Seconds a converted file is kept on disk  |
| `CONVERT_WORK_DIR`     | `/tmp/convert` | Scratch dir for inputs/outputs     |

## Security notes

- Engines are invoked with argument lists, never shell strings.
- Each job runs in its own scratch dir under a hard subprocess timeout.
- Targets are validated against an allowlist derived from the input type.
- Downloads are served as attachments with a generic MIME type.

## Roadmap

- Documents via `pandoc`, office formats via `libreoffice` (heavier image).
- Batch / multi-file conversion.

## Deployment

Pushes to `main` deploy via GitHub Actions: the workflow SSHs into the server,
clones/pulls, and rebuilds the container.
