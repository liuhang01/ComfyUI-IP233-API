"""ComfyUI node schemas. No network access occurs during node discovery."""
import json

from .catalog import live_catalog, model_names, parse_parameters
from .client import DEFAULT_BASE_URL, DEFAULT_CATALOG_URL, Client, IP233Error, make_config
from .media import download_video_result, load_image_result, upload_images
from .tasks import query, resume_task, status, submit, wait


def json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2)


def parse_reference_urls(text):
    text = text.strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            urls = json.loads(text)
        except ValueError:
            raise IP233Error("Reference URLs must be one URL per line or a JSON string array.") from None
        if not isinstance(urls, list) or not all(isinstance(x, str) for x in urls):
            raise IP233Error("Reference URLs must be a JSON string array.")
        return urls
    return [line.strip() for line in text.splitlines() if line.strip()]


class IP233Config:
    CATEGORY = "IP233/Settings"
    RETURN_TYPES = ("IP233_CONFIG",)
    RETURN_NAMES = ("config",)
    FUNCTION = "configure"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "base_url": ("STRING", {"default": DEFAULT_BASE_URL}),
            "catalog_url": ("STRING", {"default": DEFAULT_CATALOG_URL}),
            "request_timeout": ("INT", {"default": 120, "min": 5, "max": 900}),
        }, "optional": {
            "api_key": ("STRING", {"default": "", "tooltip": "Recommended: leave blank and set IP233_API_KEY or ip233.local.json. A key typed here is saved in the workflow."}),
        }}

    def configure(self, base_url, catalog_url, request_timeout, api_key=""):
        return (make_config(api_key, base_url, catalog_url, request_timeout),)


class IP233ModelInfo:
    CATEGORY = "IP233/Settings"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("model_info_json",)
    FUNCTION = "inspect"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"config": ("IP233_CONFIG",),
                             "model_filter": ("STRING", {"default": ""})}}

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def inspect(self, config, model_filter):
        records = live_catalog(config)
        with Client(config) as client:
            accessible = client.request("GET", "/models")
        ids = {m.get("id") for m in accessible.get("data", []) if isinstance(m, dict)}
        selected = [dict(m, api_key_accessible=m["id"] in ids) for m in records
                    if not model_filter or model_filter.lower() in m["id"].lower()]
        text = json_text(selected)
        return {"ui": {"text": [text]}, "result": (text,)}


class IP233ImageParameters:
    CATEGORY = "IP233/Parameters"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("parameters_json",)
    FUNCTION = "build"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "size": ("STRING", {"default": "", "tooltip": "Blank keeps this model's default. Use Model Info to check size vs aspect_ratio."}),
            "quality": ("STRING", {"default": ""}),
            "background": (["server_default", "auto", "opaque", "transparent"],),
            "output_format": (["server_default", "png", "jpeg", "webp", "gif"],),
            "extra_json": ("STRING", {"default": "{}", "multiline": True}),
        }}

    def build(self, size, quality, background, output_format, extra_json):
        result = parse_parameters(extra_json)
        for key, value in [("size", size), ("quality", quality), ("background", background), ("output_format", output_format)]:
            if value and value != "server_default":
                result[key] = value
        return (json_text(result),)


class IP233VideoParameters:
    CATEGORY = "IP233/Parameters"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("parameters_json",)
    FUNCTION = "build"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "seconds": ("INT", {"default": 0, "min": 0, "max": 120, "tooltip": "0 keeps the model default. Published limits are validated before submission."}),
            "resolution": (["server_default", "480p", "720p", "768p", "1080p", "1440p", "2160p"],),
            "aspect_ratio": (["server_default", "16:9", "9:16", "1:1", "4:3", "3:4", "21:9", "adaptive"],),
            "extra_json": ("STRING", {"default": "{}", "multiline": True}),
        }}

    def build(self, seconds, resolution, aspect_ratio, extra_json):
        result = parse_parameters(extra_json)
        if seconds:
            result["seconds"] = seconds
        for key, value in [("resolution", resolution), ("aspect_ratio", aspect_ratio)]:
            if value != "server_default":
                result[key] = value
        return (json_text(result),)


def submission_inputs(kind):
    names = model_names(kind)
    preferred = "gpt-image-2.6" if kind == "image" else "seedance2.0-A1"
    names = ([preferred] if preferred in names else []) + [n for n in names if n != preferred]
    required = {
        "config": ("IP233_CONFIG",), "model": (names,),
        "prompt": ("STRING", {"default": "", "multiline": True}),
        "request_nonce": ("INT", {"default": 0, "min": 0, "max": 2147483647,
                                     "tooltip": "Keep fixed to reuse ComfyUI's cached task. Change deliberately to create another paid request. Not a model seed."}),
    }
    if kind == "image":
        required["mode"] = (["generate", "edit"],)
    optional = {
        "parameters_json": ("STRING", {"default": "{}", "multiline": True, "forceInput": False}),
        "reference_urls": ("STRING", {"default": "", "multiline": True}),
        "custom_model": ("STRING", {"default": "", "tooltip": "Use a newly published model ID; its live API contract must exist."}),
    }
    if kind == "video":
        optional["operation_key"] = ("STRING", {"default": "", "tooltip": "Optional Idempotency-Key. Reusing it refers to the same server operation, not a fresh video."})
    else:
        optional["reference_images"] = ("IMAGE", {"tooltip": "Local images for edit mode, only if the selected model explicitly supports multipart or Data URI references."})
    return {"required": required, "optional": optional}


class IP233ImageSubmit:
    CATEGORY = "IP233/Image"
    RETURN_TYPES = ("IP233_TASK", "STRING", "STRING")
    RETURN_NAMES = ("task", "task_id", "response_json")
    FUNCTION = "generate"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return submission_inputs("image")

    def generate(self, config, model, prompt, request_nonce, mode, parameters_json="{}", reference_urls="", custom_model="", reference_images=None):
        task = submit(config, "edit" if mode == "edit" else "image", custom_model.strip() or model,
                      prompt, parse_parameters(parameters_json), parse_reference_urls(reference_urls), local_images=reference_images)
        return {"ui": {"text": ["Task: " + (task["id"] or "synchronous")]},
                "result": (task, task["id"], json_text(task["response"]))}


class IP233VideoSubmit:
    CATEGORY = "IP233/Video"
    RETURN_TYPES = ("IP233_TASK", "STRING", "STRING")
    RETURN_NAMES = ("task", "task_id", "response_json")
    FUNCTION = "generate"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return submission_inputs("video")

    def generate(self, config, model, prompt, request_nonce, parameters_json="{}", reference_urls="", custom_model="", operation_key=""):
        task = submit(config, "video", custom_model.strip() or model, prompt,
                      parse_parameters(parameters_json), parse_reference_urls(reference_urls), operation_key)
        return {"ui": {"text": ["Task: " + task["id"]]},
                "result": (task, task["id"], json_text(task["response"]))}


class IP233ResumeTask:
    CATEGORY = "IP233/Tasks"
    RETURN_TYPES = ("IP233_TASK",)
    RETURN_NAMES = ("task",)
    FUNCTION = "resume"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"config": ("IP233_CONFIG",), "kind": (["image", "edit", "video"],),
                             "task_id": ("STRING", {"default": ""})}}

    def resume(self, config, kind, task_id):
        return (resume_task(config, kind, task_id),)


class IP233TaskStatus:
    CATEGORY = "IP233/Tasks"
    RETURN_TYPES = ("IP233_TASK", "STRING", "STRING")
    RETURN_NAMES = ("task", "status", "response_json")
    FUNCTION = "inspect"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"config": ("IP233_CONFIG",), "task": ("IP233_TASK",)}}

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def inspect(self, config, task):
        current = query(config, task)
        text = json_text(current["response"])
        return {"ui": {"text": [text]}, "result": (current, status(current["response"]), text)}


class IP233TaskWait:
    CATEGORY = "IP233/Tasks"
    RETURN_TYPES = ("IP233_TASK", "STRING")
    RETURN_NAMES = ("completed_task", "response_json")
    FUNCTION = "await_result"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"config": ("IP233_CONFIG",), "task": ("IP233_TASK",),
                             "poll_interval": ("INT", {"default": 5, "min": 1, "max": 60}),
                             "max_wait": ("INT", {"default": 1800, "min": 1, "max": 14400})}}

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def await_result(self, config, task, poll_interval, max_wait):
        complete = wait(config, task, poll_interval, max_wait)
        return (complete, json_text(complete["response"]))


class IP233ImageResult:
    CATEGORY = "IP233/Image"
    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("images", "masks", "saved_paths_json")
    FUNCTION = "load"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"config": ("IP233_CONFIG",), "task": ("IP233_TASK",)}}

    def load(self, config, task):
        if task.get("kind") not in ("image", "edit"):
            raise IP233Error("Connect an image task to Image Result.")
        complete = wait(config, task)
        images, masks, paths = load_image_result(config, complete["response"])
        return (images, masks, json_text(paths))


class IP233VideoResult:
    CATEGORY = "IP233/Video"
    RETURN_TYPES = ("VIDEO", "STRING", "STRING")
    RETURN_NAMES = ("video", "saved_path", "video_url")
    FUNCTION = "load"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"config": ("IP233_CONFIG",), "task": ("IP233_TASK",)}}

    def load(self, config, task):
        if task.get("kind") != "video":
            raise IP233Error("Connect a video task to Video Result.")
        complete = wait(config, task)
        return download_video_result(config, complete["response"], complete["id"])


class IP233UploadImage:
    CATEGORY = "IP233/References"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("reference_urls",)
    FUNCTION = "upload"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"config": ("IP233_CONFIG",), "images": ("IMAGE",)}}

    def upload(self, config, images):
        return ("\n".join(upload_images(config, images)),)
