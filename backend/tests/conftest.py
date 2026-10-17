import numpy as np
import pytest

from ahv.config import parse_config
from ahv.crypto import Vault
from ahv.db import Store
from ahv.faces import Face


def vec(seed: int) -> np.ndarray:
    v = np.random.default_rng(seed).normal(size=128).astype(np.float32)
    return v / np.linalg.norm(v)


class FakeEngine:
    """Frames are 100x100 images; the red channel of pixel (0,0) encodes how many faces,
    and pixels (0,1..) encode identity seeds for each face. Faces are laid out left to right."""

    def detect(self, frame):
        n = int(frame[0, 0, 2])
        faces = []
        for i in range(n):
            faces.append(Face(10 + i * 40, 30, 36, 36, 0.99, np.array([i], dtype=np.float32)))
        return faces

    def embed(self, frame, face):
        i = int(face.raw[0])
        return vec(int(frame[0, 1 + i, 2]))


def make_frame(*identities: int, size: int = 100) -> np.ndarray:
    f = np.full((size, size * 2, 3), 127, np.uint8)
    f[0, 0, 2] = len(identities)
    for i, ident in enumerate(identities):
        f[0, 1 + i, 2] = ident
    return f


@pytest.fixture
def vault(tmp_path):
    return Vault(tmp_path / "secret.key")


@pytest.fixture
def store(tmp_path, vault):
    s = Store(tmp_path / "data", vault)
    yield s
    s.close()


@pytest.fixture
def cfg(tmp_path):
    return parse_config(
        {
            "dashboard": {"username": "admin", "password": "s3cret-pass"},
            "data_dir": str(tmp_path / "data"),
            "recognition": {"min_frames": 2, "settle_seconds": 0.0, "min_face_px": 20},
            "cameras": {
                "front_door": {"role": "front", "source": "disabled", "log_cooldown_seconds": 60,
                               "announce_cooldown_seconds": 60},
                "indoor": {"role": "indoor", "source": "disabled", "log_cooldown_seconds": 600,
                           "announce_cooldown_seconds": 1800},
            },
        }
    )
