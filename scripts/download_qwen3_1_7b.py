"""Download Qwen3 1.7B weights into the Hugging Face cache or a local directory."""

from __future__ import annotations

import argparse

from huggingface_hub import snapshot_download

DEFAULT_MODEL_ID = "Qwen/Qwen3-1.7B"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--revision", default=None)
    parser.add_argument("--cache-dir", default=None)
    parser.add_argument("--local-dir", default=None)
    args = parser.parse_args()

    path = snapshot_download(
        repo_id=args.model_id,
        revision=args.revision,
        cache_dir=args.cache_dir,
        local_dir=args.local_dir,
    )
    print(path)


if __name__ == "__main__":
    main()
