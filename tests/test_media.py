import base64
import io
import sys
import types
from unittest.mock import Mock

import numpy as np
from PIL import Image
import pytest
import torch

from ip233 import media
from ip233.client import IP233Error, ServiceConfig


def encoded_image(color=(255, 0, 0, 128), size=(4, 3)):
    buffer = io.BytesIO()
    Image.new("RGBA", size, color).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def test_image_tensor_batch_is_not_silently_truncated():
    tensor = torch.zeros((2, 3, 4, 3), dtype=torch.float32)
    tensor[1, :, :, 1] = 1
    values = media.image_batch_png(tensor)
    assert len(values) == 2
    assert Image.open(io.BytesIO(values[1])).getpixel((0, 0)) == (0, 255, 0)


@pytest.mark.parametrize("tensor", [torch.zeros((3, 4, 3)), torch.full((1, 2, 2, 3), float("nan")), torch.ones((1, 2, 2, 3)) * 2])
def test_invalid_image_input_fails(tensor):
    with pytest.raises(IP233Error):
        media.image_batch_png(tensor)


def test_alpha_preserved_as_native_mask_and_original_file(monkeypatch, tmp_path):
    monkeypatch.setattr(media, "output_directory", lambda: tmp_path)
    images, masks, paths = media.load_image_result(ServiceConfig("key"), {"data": [{"b64_json": encoded_image()}]})
    assert images.shape == (1, 3, 4, 3)
    assert masks.shape == (1, 3, 4)
    assert torch.allclose(masks, torch.full_like(masks, 127 / 255))
    assert paths[0].endswith(".png")
    assert Image.open(paths[0]).getpixel((0, 0))[3] == 128


def test_result_parser_never_uses_reference_urls():
    assert media.result_items({"request": {"images": [{"url": "https://example.com/ref.png"}]},
                               "reference_image_urls": ["https://example.com/ref.png"]}) == []


def test_gif_frames_keep_raw_animation(monkeypatch, tmp_path):
    monkeypatch.setattr(media, "output_directory", lambda: tmp_path)
    buffer = io.BytesIO()
    frames = [Image.new("RGB", (4, 3), color) for color in ("red", "green")]
    frames[0].save(buffer, "GIF", save_all=True, append_images=frames[1:], duration=100, loop=0)
    images, masks, paths = media.load_image_result(ServiceConfig("key"), {"data": [{"b64_json": base64.b64encode(buffer.getvalue()).decode()}]})
    assert images.shape[0] == 2
    assert masks.sum() == 0
    assert paths[0].endswith(".gif")
    assert Image.open(paths[0]).n_frames == 2


def test_upload_tokens_are_not_misrepresented_as_urls(monkeypatch):
    monkeypatch.setattr(media.Client, "request", Mock(return_value={"data": {"token": "upload-only-token"}}))
    with pytest.raises(IP233Error, match="tokens"):
        media.upload_images(ServiceConfig("key"), torch.zeros((1, 2, 2, 3)))


def test_video_uses_native_video_wrapper_and_original_api_content(monkeypatch, tmp_path):
    monkeypatch.setattr(media, "output_directory", lambda: tmp_path)
    native = types.ModuleType("comfy_api.input_impl")
    class VideoFromFile:
        def __init__(self, path):
            self.path = path
    native.VideoFromFile = VideoFromFile
    monkeypatch.setitem(sys.modules, "comfy_api", types.ModuleType("comfy_api"))
    monkeypatch.setitem(sys.modules, "comfy_api.input_impl", native)
    seen = []
    def download(self, url, path, max_bytes):
        seen.append(url)
        path.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"0" * 32)
    monkeypatch.setattr(media.Client, "download", download)
    video, path, url = media.download_video_result(ServiceConfig("key"), {"status": "completed"}, "task/one")
    assert isinstance(video, VideoFromFile)
    assert video.path == path
    assert seen == ["https://api-new.ip233.com/v1/videos/task%2Fone/content"]
