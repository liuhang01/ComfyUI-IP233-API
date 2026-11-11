"""Generate paired ComfyUI canvas and API examples from node schemas."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ip233 import nodes as node_module


def build(name, definitions, edges):
    nodes, prompt, links = [], {}, []
    for number, (class_name, position, overrides) in enumerate(definitions, 1):
        if class_name == "SaveImage":
            fields = {"required": {"images": ("IMAGE",), "filename_prefix": ("STRING", {"default": "IP233/image"})}}
            return_types, return_names = [], []
        else:
            cls = getattr(node_module, class_name)
            fields = cls.INPUT_TYPES()
            return_types, return_names = cls.RETURN_TYPES, cls.RETURN_NAMES
        inputs, values, api_inputs = [], [], {}
        for section in ("required", "optional"):
            for key, spec in fields.get(section, {}).items():
                kind = spec[0]
                settings = spec[1] if len(spec) > 1 else {}
                if isinstance(kind, list) or kind in ("STRING", "INT", "FLOAT", "BOOLEAN"):
                    value = overrides.get(key, settings.get("default", kind[0] if isinstance(kind, list) else ""))
                    values.append(value)
                    api_inputs[key] = value
                else:
                    inputs.append({"name": key, "type": kind, "link": None})
        outputs = [{"name": label, "type": kind, "links": []} for kind, label in zip(return_types, return_names)]
        nodes.append({
            "id": number, "type": class_name, "pos": position, "size": [330, 420 if "Submit" in class_name else 240],
            "flags": {}, "order": number - 1, "mode": 0, "inputs": inputs, "outputs": outputs,
            "properties": {"Node name for S&R": class_name}, "widgets_values": values,
        })
        prompt[str(number)] = {"class_type": class_name, "inputs": api_inputs}
    for identity, (source, slot, target, key) in enumerate(edges, 1):
        target_node, source_node = nodes[target - 1], nodes[source - 1]
        target_slot = next(i for i, entry in enumerate(target_node["inputs"]) if entry["name"] == key)
        kind = source_node["outputs"][slot]["type"]
        target_node["inputs"][target_slot]["link"] = identity
        source_node["outputs"][slot]["links"].append(identity)
        links.append([identity, source, slot, target, target_slot, kind])
        prompt[str(target)]["inputs"][key] = [str(source), slot]
    workflow = {"last_node_id": len(nodes), "last_link_id": len(links), "nodes": nodes,
                "links": links, "groups": [], "config": {}, "extra": {}, "version": 0.4}
    for folder, payload in [("workflows", workflow), ("api", prompt)]:
        directory = ROOT / "examples" / folder
        directory.mkdir(parents=True, exist_ok=True)
        (directory / (name + ".json")).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    config = ("IP233Config", [40, 80], {})
    image = ("IP233ImageSubmit", [430, 80], {"prompt": "A small green robot on a clean studio background"})
    result = ("IP233ImageResult", [830, 80], {})
    save = ("SaveImage", [1230, 80], {})
    image_edges = [(1, 0, 2, "config"), (1, 0, 3, "config"), (2, 0, 3, "task"), (3, 0, 4, "images")]
    build("image_generate", [config, image, result, save], image_edges)
    edit = ("IP233ImageSubmit", [430, 80], {"prompt": "Change the background to a green studio wall", "mode": "edit"})
    build("image_edit", [config, edit, result, save], image_edges)
    video = ("IP233VideoSubmit", [430, 80], {"prompt": "A sailboat on a calm sea at sunrise, slow forward camera movement"})
    video_result = ("IP233VideoResult", [830, 80], {})
    task_edges = [(1, 0, 2, "config"), (1, 0, 3, "config"), (2, 0, 3, "task")]
    build("video_generate", [config, video, video_result], task_edges)
    resume = ("IP233ResumeTask", [430, 80], {"kind": "video"})
    build("video_resume", [config, resume, video_result], task_edges)
    print("Built 4 canvas workflows and 4 API prompts; no API keys included.")


if __name__ == "__main__":
    main()
