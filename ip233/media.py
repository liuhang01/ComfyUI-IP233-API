"""Native IMAGE/MASK/VIDEO conversion and bounded media downloads."""
from __future__ import annotations

import base64
import io
import uuid
from pathlib import Path
from urllib.parse import quote

from .client import Client, IP233Error, check_interrupt, secure_url
from .tasks import inner_response, output_directory


def image_batch_png(images):
    import numpy as np
    from PIL import Image
    value = images.detach().cpu().numpy() if hasattr(images, "detach") else np.asarray(images)
    if value.ndim != 4 or any(size < 1 for size in value.shape) or value.shape[-1] not in (3, 4):
        raise IP233Error("IMAGE input must have shape [batch,height,width,3 or 4].")
    if value.shape[0] > 30 or value.shape[1] * value.shape[2] > 32_000_000:
        raise IP233Error("Reference input exceeds 30 images or 32 megapixels per image.")
    if not np.isfinite(value).all() or value.min() < 0 or value.max() > 1:
        raise IP233Error("IMAGE input must contain finite values in [0,1].")
    encoded = []
    for item in value:
        check_interrupt()
        buffer = io.BytesIO()
        Image.fromarray(np.rint(item * 255).astype(np.uint8)).save(buffer, format="PNG")
        if buffer.tell() > 32 * 1024 * 1024:
            raise IP233Error("Reference image exceeds 32 MiB.")
        encoded.append(buffer.getvalue())
    return encoded


def upload_images(config, images):
    urls = []
    with Client(config) as client:
        for png in image_batch_png(images):
            response = client.request("POST", "/media/uploads",
                                      files={"file": ("reference.png", png, "image/png")}, data={"kind": "image"})
            url = next((value.get(k) for value in (response, inner_response(response))
                        for k in ("url", "file_url", "public_url") if isinstance(value.get(k), str)), None)
            if not url:
                raise IP233Error("Upload did not return a public HTTPS URL. Upload tokens cannot be used in URL-only fields; supply a hosted reference URL instead.")
            urls.append(secure_url(url))
    return urls


def result_items(response):
    found = []
    for value in (response, inner_response(response)):
        for key in ("result_url", "video_url", "download_url", "output_url"):
            if isinstance(value.get(key), str) and value[key]:
                found.append({"url": value[key]})
        if value is not response and (value.get("url") or value.get("b64_json")):
            found.append(value)
        for key in ("data", "output", "images"):
            if isinstance(value.get(key), list):
                found.extend(x for x in value[key] if isinstance(x, dict) and (x.get("url") or x.get("b64_json") or x.get("video_url")))
    unique, seen = [], set()
    for item in found:
        identity = item.get("url") or item.get("video_url") or item.get("b64_json")
        if identity not in seen:
            unique.append(item)
            seen.add(identity)
    return unique


def load_image_result(config, response):
    import numpy as np
    import torch
    from PIL import Image, ImageOps, ImageSequence, UnidentifiedImageError
    items = result_items(response)
    if not items:
        raise IP233Error("Completed image task returned no result URL or base64 image. Query it again before resubmitting.")
    images, masks, paths, shape, total_pixels = [], [], [], None, 0
    with Client(config) as client:
        for item in items:
            check_interrupt()
            path = output_directory() / (uuid.uuid4().hex + ".image")
            if item.get("b64_json"):
                try:
                    raw = item["b64_json"]
                    if len(raw) > 96 * 1024 * 1024:
                        raise IP233Error("Base64 image is too large.")
                    content = base64.b64decode(raw, validate=True)
                except (ValueError, TypeError):
                    raise IP233Error("Invalid base64 image result.") from None
                path.write_bytes(content)
            else:
                client.download(item.get("url"), path, max_bytes=64 * 1024 * 1024)
            try:
                with Image.open(path) as source:
                    extension = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp", "GIF": ".gif"}.get(source.format)
                    if not extension:
                        raise IP233Error("Unsupported generated image format.")
                    if getattr(source, "n_frames", 1) > 64:
                        raise IP233Error("Animation exceeds 64 frames; the original file was preserved.")
                    if source.width * source.height > 32_000_000:
                        raise IP233Error("Generated image exceeds 32 megapixels.")
                    for frame in ImageSequence.Iterator(source):
                        check_interrupt()
                        total_pixels += source.width * source.height
                        if total_pixels > 32_000_000:
                            raise IP233Error("Decoded image batch exceeds 32 megapixels in total; use the preserved original file for large animations.")
                        rgba = ImageOps.exif_transpose(frame).convert("RGBA")
                        array = np.array(rgba, dtype=np.float32) / 255.0
                        if shape is not None and shape != array.shape[:2]:
                            raise IP233Error("Result frames have different sizes and cannot form a ComfyUI IMAGE batch. Original files remain in output/ip233.")
                        shape = array.shape[:2]
                        images.append(torch.from_numpy(array[:, :, :3].copy()))
                        masks.append(torch.from_numpy(1.0 - array[:, :, 3].copy()))
            except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
                raise IP233Error("Result is not a supported or safe image file.") from exc
            final = path.with_suffix(extension)
            path.replace(final)
            paths.append(str(final))
    return torch.stack(images), torch.stack(masks), paths


def download_video_result(config, response, identity):
    items = result_items(response)
    url = next((x.get("url") or x.get("video_url") for x in items if x.get("url") or x.get("video_url")), None)
    if not url and identity:
        url = config.base_url + "/videos/" + quote(str(identity), safe="") + "/content"
    if not url:
        raise IP233Error("Completed video task returned no result or task ID.")
    path = output_directory() / (uuid.uuid4().hex + ".mp4")
    with Client(config) as client:
        client.download(url, path, max_bytes=1024 * 1024 * 1024)
    with path.open("rb") as handle:
        header = handle.read(32)
    if not (b"ftyp" in header or header.startswith(b"\x1aE\xdf\xa3")):
        raise IP233Error("Downloaded result is not MP4/MOV/WebM video. Check the saved file and original task.")
    if header.startswith(b"\x1aE\xdf\xa3"):
        renamed = path.with_suffix(".webm")
        path.replace(renamed)
        path = renamed
    try:
        from comfy_api.input_impl import VideoFromFile
    except ImportError:
        raise IP233Error("This ComfyUI version lacks native VIDEO support. Update ComfyUI; the downloaded video is already in output/ip233.") from None
    return VideoFromFile(str(path)), str(path), url
