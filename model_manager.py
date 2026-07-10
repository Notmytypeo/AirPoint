from __future__ import annotations

from pathlib import Path
from urllib.request import Request, urlopen


MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"


def ensure_hand_model(progress=None) -> Path:
    root = Path(__file__).resolve().parent.parent
    model_dir = root / "models"
    model_dir.mkdir(exist_ok=True)
    destination = model_dir / "hand_landmarker.task"
    if destination.exists() and destination.stat().st_size > 1_000_000:
        return destination

    temporary = destination.with_suffix(".download")
    request = Request(MODEL_URL, headers={"User-Agent": "AirPoint/1.0"})
    try:
        with urlopen(request, timeout=30) as response, temporary.open("wb") as output:
            total = int(response.headers.get("Content-Length", "0"))
            received = 0
            while chunk := response.read(256 * 1024):
                output.write(chunk)
                received += len(chunk)
                if progress and total:
                    progress(min(100, round(received * 100 / total)))
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return destination
