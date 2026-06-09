"""Conversion routing for convert.

A small matrix maps each input category to the formats it can become and the
engine that does the work:

  - image  -> image : Pillow (in-process)
  - image  -> pdf   : Pillow
  - pdf    -> image : poppler-utils (pdftoppm); multi-page output is zipped
  - audio  -> audio : ffmpeg
  - video  -> video/audio/gif : ffmpeg

Engines are invoked with argument lists (never shell strings), and every
external command runs under a hard timeout.
"""

import os
import glob
import zipfile
import subprocess

from PIL import Image

TIMEOUT = 900  # 15 min ceiling for large media

MATRIX = {
    "image": {
        "ext": {"png", "jpg", "jpeg", "webp", "gif", "bmp", "tiff"},
        "targets": ["png", "jpg", "webp", "gif", "bmp", "tiff", "pdf"],
    },
    "audio": {
        "ext": {"mp3", "wav", "flac", "m4a", "ogg", "aac"},
        "targets": ["mp3", "wav", "flac", "m4a", "ogg", "aac"],
    },
    "video": {
        "ext": {"mp4", "mov", "webm", "mkv", "avi", "flv", "m4v"},
        "targets": ["mp4", "webm", "mkv", "gif", "mp3", "m4a", "wav"],
    },
    "pdf": {
        "ext": {"pdf"},
        "targets": ["png", "jpg"],
    },
}

PIL_FORMAT = {
    "jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "webp": "WEBP",
    "gif": "GIF", "bmp": "BMP", "tiff": "TIFF", "pdf": "PDF",
}


def _norm(ext):
    return ext.lower().lstrip(".")


def category_for_ext(ext):
    e = _norm(ext)
    for category, spec in MATRIX.items():
        if e in spec["ext"]:
            return category
    return None


def targets_for_ext(ext):
    """Return (category, [targets]) for an input extension, minus same-format."""
    category = category_for_ext(ext)
    if not category:
        return None, []
    e = _norm(ext)
    same = {"jpg", "jpeg"} if e in ("jpg", "jpeg") else {e}
    return category, [t for t in MATRIX[category]["targets"] if t not in same]


def convert(input_path, src_ext, target, out_dir):
    """Convert input_path to target, returning the output file path."""
    category = category_for_ext(src_ext)
    if not category:
        raise ValueError("unsupported input type")
    target = _norm(target)
    if target not in MATRIX[category]["targets"]:
        raise ValueError("unsupported target for this input")

    if category == "image":
        return _image(input_path, target, out_dir)
    if category == "pdf":
        return _pdf(input_path, target, out_dir)
    return _ffmpeg(category, input_path, target, out_dir)


def _image(input_path, target, out_dir):
    out = os.path.join(out_dir, "output." + target)
    fmt = PIL_FORMAT[target]
    with Image.open(input_path) as im:
        # formats without alpha need a flat RGB image
        if fmt in ("JPEG", "PDF", "BMP") and im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGB")
        kwargs = {"quality": 92} if fmt == "JPEG" else {}
        im.save(out, fmt, **kwargs)
    return out


def _ffmpeg(category, input_path, target, out_dir):
    out = os.path.join(out_dir, "output." + target)
    args = ["ffmpeg", "-y", "-i", input_path]
    if category == "video" and target in ("mp3", "m4a", "wav", "ogg", "aac", "flac"):
        args.append("-vn")  # extract audio only
    args.append(out)
    _run(args)
    return out


def _pdf(input_path, target, out_dir):
    base = os.path.join(out_dir, "page")
    flag = "-png" if target == "png" else "-jpeg"
    _run(["pdftoppm", flag, "-r", "150", input_path, base])

    ext = "jpg" if target == "jpg" else "png"
    pages = sorted(glob.glob(base + "-*." + ext))
    if not pages:
        raise RuntimeError("no pages produced")
    if len(pages) == 1:
        return pages[0]

    archive = os.path.join(out_dir, "output.zip")
    with zipfile.ZipFile(archive, "w") as zf:
        for i, page in enumerate(pages, 1):
            zf.write(page, f"page-{i}.{ext}")
    return archive


def _run(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
    if result.returncode != 0:
        lines = [line.strip() for line in result.stderr.splitlines() if line.strip()]
        raise RuntimeError(lines[-1] if lines else "conversion failed")
