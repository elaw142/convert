import os
import re
import uuid
import time
import shutil
import threading

from flask import Flask, request, jsonify, send_file, render_template

import converters

app = Flask(__name__)

MAX_FILE_MB = int(os.environ.get("CONVERT_MAX_FILE_MB", "1024"))
TTL = int(os.environ.get("CONVERT_TTL", "600"))  # seconds before output auto-deletes
WORK_DIR = os.environ.get("CONVERT_WORK_DIR", os.path.join(os.path.dirname(__file__), "work"))

app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_MB * 1024 * 1024
os.makedirs(WORK_DIR, exist_ok=True)

jobs = {}


def safe_stem(name):
    stem = os.path.splitext(os.path.basename(name or ""))[0].strip()
    stem = re.sub(r"[\x00-\x1f\x7f]", "", stem)
    return stem or "output"


def cleanup_dir(path, delay=TTL):
    def remove():
        time.sleep(delay)
        shutil.rmtree(path, ignore_errors=True)
    threading.Thread(target=remove, daemon=True).start()


def do_convert(job_id, in_path, ext, target, job_dir):
    job = jobs[job_id]
    try:
        out = converters.convert(in_path, ext, target, job_dir)
        out_ext = "zip" if out.endswith(".zip") else target
        job["path"] = out
        job["out_size"] = os.path.getsize(out)
        job["download_name"] = f"{job['stem']}.{out_ext}"
        job["status"] = "done"
    except Exception as exc:
        job["status"] = "error"
        job["error"] = str(exc)
    finally:
        # Remove the input promptly; keep the output around for the TTL window.
        try:
            os.remove(in_path)
        except OSError:
            pass
        cleanup_dir(job_dir)


@app.route("/")
def index():
    return render_template("index.html", max_file_mb=MAX_FILE_MB, ttl=TTL)


@app.route("/api/targets")
def targets():
    ext = request.args.get("ext", "")
    category, allowed = converters.targets_for_ext(ext)
    return jsonify({"category": category, "targets": allowed})


@app.route("/api/convert", methods=["POST"])
def convert_route():
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "no file provided"}), 400

    target = (request.form.get("target") or "").lower()
    ext = os.path.splitext(file.filename)[1].lstrip(".").lower()

    category, allowed = converters.targets_for_ext(ext)
    if not category:
        return jsonify({"error": f"unsupported input type: .{ext or '?'}"}), 400
    if target not in allowed:
        return jsonify({"error": "unsupported target for this input"}), 400

    job_id = str(uuid.uuid4())
    job_dir = os.path.join(WORK_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)
    in_path = os.path.join(job_dir, "input." + ext)
    file.save(in_path)

    jobs[job_id] = {
        "status": "processing",
        "stem": safe_stem(file.filename),
        "src_ext": ext,
        "target": target,
        "in_size": os.path.getsize(in_path),
    }
    threading.Thread(
        target=do_convert, args=(job_id, in_path, ext, target, job_dir), daemon=True
    ).start()

    return jsonify({"job_id": job_id})


@app.route("/api/status/<job_id>")
def status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "job not found"}), 404
    if job["status"] == "done":
        return jsonify({
            "status": "done",
            "in_size": job["in_size"],
            "out_size": job["out_size"],
            "download_name": job["download_name"],
        })
    if job["status"] == "error":
        return jsonify({"status": "error", "error": job["error"]})
    return jsonify({"status": "processing"})


@app.route("/api/file/<job_id>")
def get_file(job_id):
    job = jobs.get(job_id)
    if not job or job["status"] != "done" or not os.path.exists(job.get("path", "")):
        return jsonify({"error": "file not ready"}), 404
    return send_file(
        job["path"],
        as_attachment=True,
        download_name=job["download_name"],
        mimetype="application/octet-stream",
    )


@app.errorhandler(413)
def too_large(_):
    return jsonify({"error": f"file exceeds {MAX_FILE_MB}MB limit"}), 413


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5011, threaded=True, debug=False)
