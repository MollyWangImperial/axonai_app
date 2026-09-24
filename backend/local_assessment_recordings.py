"""Authenticated, loopback-only review files. Never sends video to cloud storage."""
import asyncio
import json
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

from backend import server

router = APIRouter(prefix="/api/local-assessment-recordings")
RECORDINGS_DIR = Path(__file__).resolve().parent / ".local_state" / "assessment-recordings"
MAX_VIDEO_BYTES = 1024 * 1024 * 1024
ID_PATTERN = re.compile(r"^\d{8}T\d{6}Z_[A-Z]\d+_[a-f0-9]{12}$")


async def owner(request, uid=""):
    if not request.client or request.client.host not in {"127.0.0.1", "::1"} or request.url.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise HTTPException(404, "Local recording service is only available on this computer")
    user = await server._task_video_user(request, uid)
    if not user:
        raise HTTPException(401, "Sign in required")
    return user["id"]


def read_record(recording_id, user_id):
    if not ID_PATTERN.fullmatch(recording_id):
        raise HTTPException(404, "Recording not found")
    path = RECORDINGS_DIR / f"{recording_id}.json"
    if not path.is_file():
        raise HTTPException(404, "Recording not found")
    record = json.loads(path.read_text(encoding="utf-8"))
    if record["user_id"] != user_id:
        raise HTTPException(404, "Recording not found")
    return record


def write_record(record):
    path = RECORDINGS_DIR / f"{record['id']}.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def public_record(record):
    return {key: record[key] for key in ("id", "status", "task_id", "filename", "path", "evidence_path", "duration_ms", "size_bytes", "content_type")}


@router.post("")
async def save_recording(request: Request, task_id: str, duration_ms: int = 0):
    user_id = await owner(request)
    if task_id not in server.ASSESSMENT_RUBRICS:
        raise HTTPException(422, "Unknown assessment task")
    mime = request.headers.get("content-type", "").split(";", 1)[0].lower()
    if mime not in {"video/webm", "video/mp4"}:
        raise HTTPException(415, "Use WebM or MP4 video")
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    recording_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_{task_id}_{uuid.uuid4().hex[:12]}"
    filename = f"{recording_id}.{'mp4' if mime == 'video/mp4' else 'webm'}"
    path = RECORDINGS_DIR / filename
    temporary = path.with_suffix(path.suffix + ".part")
    size = 0
    header = b""
    try:
        with temporary.open("xb") as output:
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_VIDEO_BYTES:
                    raise HTTPException(413, "Recording exceeds the 1 GB local file limit")
                header = (header + chunk)[:32] if len(header) < 32 else header
                output.write(chunk)
        if not (header.startswith(b"\x1a\x45\xdf\xa3") if mime == "video/webm" else header[4:8] == b"ftyp"):
            raise HTTPException(415, "The recording has no valid video header")
        # Browser WebM streams often omit a seek index. Remux without changing
        # the frames when the local FFmpeg installation is available.
        seekable = False
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            try:
                completed = await asyncio.to_thread(subprocess.run,
                    [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(temporary), "-map", "0:v:0", "-c", "copy", str(path)],
                    capture_output=True, timeout=90, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                seekable = completed.returncode == 0 and path.is_file() and path.stat().st_size > 0
            except (OSError, subprocess.TimeoutExpired):
                pass
        if not seekable:
            temporary.replace(path)
        record = {"id": recording_id, "user_id": user_id, "task_id": task_id, "status": "video_saved",
                  "filename": filename, "path": str(path.resolve()), "evidence_path": str((RECORDINGS_DIR / f"{recording_id}.json").resolve()),
                  "duration_ms": max(0, duration_ms), "size_bytes": path.stat().st_size, "content_type": mime, "seek_index_finalized": seekable,
                  "created_at": datetime.now(timezone.utc).isoformat()}
        write_record(record)
        return public_record(record)
    finally:
        temporary.unlink(missing_ok=True)


@router.post("/{recording_id}/evidence")
async def save_evidence(recording_id: str, request: Request):
    record = read_record(recording_id, await owner(request))
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > 4 * 1024 * 1024:
            raise HTTPException(413, "Evidence exceeds the local limit")
    try:
        evidence = json.loads(data)
        task = server.TaskResult.model_validate(evidence["task_result"])
        if task.task_id != record["task_id"]:
            raise ValueError("Task mismatch")
        expected = {s["id"] for s in server.ASSESSMENT_RUBRICS[task.task_id]["steps"]}
        ids = [s.step_id for s in task.steps]
        if len(ids) != len(set(ids)) or not set(ids).issubset(expected):
            raise ValueError("Step mismatch")
        report = server.testing_task_report(task, server.ASSESSMENT_RUBRICS)
        record.update(status="saved", evidence=evidence, score_report=report)
        write_record(record)
    except (ValueError, KeyError, TypeError) as error:
        raise HTTPException(422, "Invalid recording evidence") from error
    return public_record(record)


@router.api_route("/{recording_id}/video", methods=["GET", "HEAD"])
async def play_recording(recording_id: str, request: Request, uid: str = ""):
    record = read_record(recording_id, await owner(request, uid))
    # Filename was generated here; never accept a client-supplied path.
    path = RECORDINGS_DIR / record["filename"]
    size = path.stat().st_size
    headers = {"Cache-Control": "no-store", "Accept-Ranges": "bytes", "Content-Length": str(size)}
    if request.method == "HEAD":
        return Response(media_type=record["content_type"], headers=headers)
    byte_range = request.headers.get("range")
    if not byte_range:
        return FileResponse(path, media_type=record["content_type"], headers=headers)
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", byte_range)
    if not match or not any(match.groups()):
        return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
    low, high = match.groups()
    start = int(low) if low else max(0, size - int(high))
    end = min(size - 1, int(high)) if low and high else size - 1
    if start > end or start >= size:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
    def section():
        with path.open("rb") as source:
            source.seek(start)
            remaining = end - start + 1
            while remaining:
                data = source.read(min(65536, remaining))
                if not data:
                    break
                remaining -= len(data)
                yield data
    headers.update({"Content-Length": str(end - start + 1), "Content-Range": f"bytes {start}-{end}/{size}"})
    return StreamingResponse(section(), status_code=206, media_type=record["content_type"], headers=headers)
