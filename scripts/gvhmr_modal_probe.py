from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import modal


APP_NAME = "gvhmr-probe"
REPO_LOCAL = Path(__file__).resolve().parents[1] / "external" / "upstream-GVHMR"
REPO_REMOTE = "/root/GVHMR"
CACHE_ROOT = Path("/cache")
CRF = 23

app = modal.App(APP_NAME)
cache_volume = modal.Volume.from_name("gvhmr-cache", create_if_missing=True)

image = (
    modal.Image.from_registry(
        "nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04",
        add_python="3.10",
    )
    .apt_install(
        "build-essential",
        "clang",
        "git",
        "ffmpeg",
        "aria2",
        "curl",
        "libgl1",
        "libglib2.0-0",
        "libsm6",
        "libxext6",
        "libxrender1",
    )
    .add_local_dir(REPO_LOCAL, REPO_REMOTE, copy=True)
    .run_commands(
        f"cd {REPO_REMOTE} && python -m pip install --upgrade pip setuptools wheel",
        (
            f"cd {REPO_REMOTE} && "
            "grep -Ev '^(pycolmap|chumpy|jupyter|matplotlib|ipdb|black|tensorboardX)$' "
            "requirements.txt > requirements.modal.txt"
        ),
        f"cd {REPO_REMOTE} && python -m pip install -r requirements.modal.txt",
        f"cd {REPO_REMOTE} && python -m pip install --no-build-isolation chumpy",
        f"cd {REPO_REMOTE} && python -m pip install yacs",
        f"cd {REPO_REMOTE} && python -m pip install 'fastapi[standard]'",
        f"cd {REPO_REMOTE} && python -m pip install -e .",
    )
    .env({"PYTHONUNBUFFERED": "1"})
)


WEIGHTS = {
    "body_models/smpl/SMPL_NEUTRAL.pkl": "https://huggingface.co/camenduru/SMPLer-X/resolve/main/SMPL_NEUTRAL.pkl",
    "body_models/smplx/SMPLX_NEUTRAL.npz": "https://huggingface.co/camenduru/SMPLer-X/resolve/main/SMPLX_NEUTRAL.npz",
    "gvhmr/gvhmr_siga24_release.ckpt": "https://huggingface.co/camenduru/GVHMR/resolve/main/gvhmr/gvhmr_siga24_release.ckpt",
    "hmr2/epoch=10-step=25000.ckpt": "https://huggingface.co/camenduru/GVHMR/resolve/main/hmr2/epoch%3D10-step%3D25000.ckpt",
    "vitpose/vitpose-h-multi-coco.pth": "https://huggingface.co/camenduru/GVHMR/resolve/main/vitpose/vitpose-h-multi-coco.pth",
    "yolo/yolov8x.pt": "https://huggingface.co/camenduru/GVHMR/resolve/main/yolo/yolov8x.pt",
}


def _ensure_repo_on_path() -> None:
    if REPO_REMOTE not in sys.path:
        sys.path.insert(0, REPO_REMOTE)
    os.chdir(REPO_REMOTE)


def _ensure_checkpoints() -> None:
    checkpoints_root = CACHE_ROOT / "checkpoints"
    checkpoints_root.mkdir(parents=True, exist_ok=True)

    for relative_path, url in WEIGHTS.items():
        destination = checkpoints_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and destination.stat().st_size > 0:
            continue
        print(f"downloading {relative_path}")
        urllib.request.urlretrieve(url, destination)

    repo_inputs = Path(REPO_REMOTE) / "inputs"
    repo_inputs.mkdir(parents=True, exist_ok=True)
    repo_checkpoints = repo_inputs / "checkpoints"
    if repo_checkpoints.is_symlink() or repo_checkpoints.exists():
        if repo_checkpoints.is_symlink():
            current = os.readlink(repo_checkpoints)
            if current == str(checkpoints_root):
                return
            repo_checkpoints.unlink()
        else:
            return
    repo_checkpoints.symlink_to(checkpoints_root, target_is_directory=True)
    try:
        cache_volume.commit()
    except Exception:
        pass


def _download_video(video_url: str) -> Path:
    parsed = urllib.parse.urlparse(video_url)
    suffix = Path(parsed.path).suffix or ".mp4"
    digest = hashlib.sha256(video_url.encode("utf-8")).hexdigest()[:16]
    video_dir = CACHE_ROOT / "videos"
    video_dir.mkdir(parents=True, exist_ok=True)
    local_path = video_dir / f"{digest}{suffix}"
    if not local_path.exists() or local_path.stat().st_size == 0:
        print(f"downloading video: {video_url}")
        urllib.request.urlretrieve(video_url, local_path)
        try:
            cache_volume.commit()
        except Exception:
            pass
    return local_path


def _prepare_cfg(video_path: Path, static_cam: bool, run_id: str):
    from hydra import compose, initialize_config_module
    from hmr4d.configs import register_store_gvhmr
    from hmr4d.utils.pylogger import Log
    from hmr4d.utils.video_io_utils import get_video_lwh, get_video_reader, get_writer

    output_root = CACHE_ROOT / "outputs"
    output_root.mkdir(parents=True, exist_ok=True)

    with initialize_config_module(version_base="1.3", config_module="hmr4d.configs"):
        overrides = [
            f"video_name={run_id}",
            f"static_cam={static_cam}",
            "verbose=False",
            f"output_root={str(output_root)}",
        ]
        register_store_gvhmr()
        cfg = compose(config_name="demo", overrides=overrides)

    Path(cfg.output_dir).mkdir(parents=True, exist_ok=True)
    Path(cfg.preprocess_dir).mkdir(parents=True, exist_ok=True)

    Log.info(f"[Input]: {video_path}")
    length, width, height = get_video_lwh(video_path)
    Log.info(f"(L, W, H) = ({length}, {width}, {height})")
    Log.info(f"[Output Dir]: {cfg.output_dir}")

    if not Path(cfg.video_path).exists():
        reader = get_video_reader(video_path)
        writer = get_writer(cfg.video_path, fps=30, crf=CRF)
        for frame in reader:
            writer.write_frame(frame)
        writer.close()
        reader.close()

    return cfg


def _load_preproc_classes():
    import types

    preproc_root = Path(REPO_REMOTE) / "hmr4d" / "utils" / "preproc"
    package_name = "hmr4d.utils.preproc"

    package = sys.modules.get(package_name)
    if package is None:
        package = types.ModuleType(package_name)
        package.__path__ = [str(preproc_root)]
        sys.modules[package_name] = package

    def load_module(module_name: str, filename: str):
        if module_name in sys.modules:
            return sys.modules[module_name]

        spec = importlib.util.spec_from_file_location(module_name, preproc_root / filename)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load {module_name} from {filename}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module

    tracker_mod = load_module("hmr4d.utils.preproc.tracker", "tracker.py")
    vitfeat_mod = load_module("hmr4d.utils.preproc.vitfeat_extractor", "vitfeat_extractor.py")
    vitpose_mod = load_module("hmr4d.utils.preproc.vitpose", "vitpose.py")

    return tracker_mod.Tracker, vitpose_mod.VitPoseExtractor, vitfeat_mod.Extractor


def _tensor_summary(value: Any) -> dict[str, Any]:
    import torch

    if not isinstance(value, torch.Tensor):
        return {"type": str(type(value))}

    flat = value.detach().cpu().reshape(-1)
    sample = flat[: min(6, flat.numel())].tolist()
    return {
        "shape": list(value.shape),
        "dtype": str(value.dtype),
        "sample": sample,
    }


def _build_summary(pred: dict[str, Any], *, video_url: str, run_id: str, static_cam: bool, timings: dict[str, float]) -> dict[str, Any]:
    from hmr4d.utils.video_io_utils import get_video_lwh

    output_dir = CACHE_ROOT / "outputs" / run_id
    raw_path = output_dir / "hmr4d_results.pt"
    artifact_path = output_dir / "summary.json"

    summary = {
        "run_id": run_id,
        "video_url": video_url,
        "static_cam": static_cam,
        "artifacts": {
            "raw_torch_path": str(raw_path),
            "summary_json_path": str(artifact_path),
        },
        "timings_s": timings,
        "video": {},
        "smpl_params_global": {k: _tensor_summary(v) for k, v in pred["smpl_params_global"].items()},
        "smpl_params_incam": {k: _tensor_summary(v) for k, v in pred["smpl_params_incam"].items()},
    }

    if raw_path.exists():
        summary["video"]["generated_from"] = str(raw_path)

    copied_video = output_dir / "0_input_video.mp4"
    if copied_video.exists():
        length, width, height = get_video_lwh(copied_video)
        summary["video"].update(
            {
                "frames": int(length),
                "width": int(width),
                "height": int(height),
                "fps_assumed": 30,
                "duration_s_estimate": round(length / 30, 3),
            }
        )

    artifact_path.write_text(json.dumps(summary, indent=2))
    try:
        cache_volume.commit()
    except Exception:
        pass
    return summary


def _run_inference(video_url: str, static_cam: bool = True) -> dict[str, Any]:
    import hydra
    import torch
    from hmr4d.model.gvhmr.gvhmr_pl_demo import DemoPL
    from hmr4d.utils.net_utils import detach_to_cpu
    from hmr4d.utils.pylogger import Log
    from hmr4d.utils.video_io_utils import get_video_lwh
    from hmr4d.utils.geo.hmr_cam import get_bbx_xys_from_xyxy, estimate_K
    from hmr4d.utils.geo_transform import compute_cam_angvel

    _ensure_repo_on_path()
    _ensure_checkpoints()
    Tracker, VitPoseExtractor, Extractor = _load_preproc_classes()

    local_video_path = _download_video(video_url)
    run_id = hashlib.sha256(f"{video_url}|{static_cam}".encode("utf-8")).hexdigest()[:16]
    cfg = _prepare_cfg(local_video_path, static_cam, run_id)
    paths = cfg.paths

    timings: dict[str, float] = {}

    preprocess_start = time.perf_counter()
    if not Path(paths.bbx).exists():
        tracker = Tracker()
        bbx_xyxy = tracker.get_one_track(str(local_video_path)).float()
        bbx_xys = get_bbx_xys_from_xyxy(bbx_xyxy, base_enlarge=1.2).float()
        torch.save({"bbx_xyxy": bbx_xyxy, "bbx_xys": bbx_xys}, paths.bbx)
    else:
        bbx_xys = torch.load(paths.bbx)["bbx_xys"]

    if not Path(paths.vitpose).exists():
        vitpose_extractor = VitPoseExtractor()
        vitpose = vitpose_extractor.extract(str(local_video_path), bbx_xys)
        torch.save(vitpose, paths.vitpose)
    else:
        vitpose = torch.load(paths.vitpose)

    if not Path(paths.vit_features).exists():
        extractor = Extractor()
        vit_features = extractor.extract_video_features(str(local_video_path), bbx_xys)
        torch.save(vit_features, paths.vit_features)
    else:
        vit_features = torch.load(paths.vit_features)

    length, width, height = get_video_lwh(str(local_video_path))
    K_fullimg = estimate_K(width, height).repeat(length, 1, 1)
    if static_cam:
        R_w2c = torch.eye(3).repeat(length, 1, 1)
    else:
        raise RuntimeError("Dynamic camera mode is intentionally disabled in this probe.")

    data = {
        "length": torch.tensor(length),
        "bbx_xys": bbx_xys,
        "kp2d": vitpose,
        "K_fullimg": K_fullimg,
        "cam_angvel": compute_cam_angvel(R_w2c),
        "f_imgseq": vit_features,
    }
    timings["preprocess"] = round(time.perf_counter() - preprocess_start, 3)

    predict_start = time.perf_counter()
    model: DemoPL = hydra.utils.instantiate(cfg.model, _recursive_=False)
    model.load_pretrained_model(cfg.ckpt_path)
    model = model.eval().cuda()
    pred = model.predict(data, static_cam=static_cam)
    pred = detach_to_cpu(pred)
    timings["predict"] = round(time.perf_counter() - predict_start, 3)

    raw_path = Path(paths.hmr4d_results)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(pred, raw_path)

    summary = _build_summary(
        pred,
        video_url=video_url,
        run_id=run_id,
        static_cam=static_cam,
        timings=timings,
    )

    Log.info(json.dumps(summary, indent=2))
    return summary


@app.function(
    image=image,
    gpu="A10G",
    timeout=1800,
    volumes={"/cache": cache_volume},
    cpu=8,
    memory=32768,
    scaledown_window=900,
)
def run_probe(video_url: str, static_cam: bool = True) -> dict[str, Any]:
    return _run_inference(video_url=video_url, static_cam=static_cam)


@app.function(
    image=image,
    gpu="A10G",
    timeout=1800,
    volumes={"/cache": cache_volume},
    cpu=8,
    memory=32768,
    scaledown_window=900,
)
@modal.fastapi_endpoint(method="GET", docs=True)
def probe_api(video_url: str, static_cam: bool = True) -> dict[str, Any]:
    return _run_inference(video_url=video_url, static_cam=static_cam)


@app.local_entrypoint()
def batch_test() -> None:
    clip_urls = [
        "https://raw.githubusercontent.com/zju3dv/GVHMR/main/docs/example_video/tennis.mp4",
        "https://huggingface.co/spaces/LittleFrog/GVHMR/resolve/main/examples/cxk.mp4",
    ]
    results = []
    for video_url in clip_urls:
        print(f"running probe for {video_url}")
        result = run_probe.remote(video_url=video_url, static_cam=True)
        results.append(result)
        print(json.dumps(result, indent=2))

    output_path = Path(__file__).resolve().parents[1] / "tmp_clips" / "gvhmr_modal_results.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(results, indent=2))
    print(f"wrote {output_path}")
