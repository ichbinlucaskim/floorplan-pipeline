import pytest


@pytest.fixture
def sample_rooms():
    """Two adjacent rooms (living + bedroom) sharing an interior wall, with a
    door on the shared wall and a window on an exterior wall.

    Coordinates are ResPlan-style pixels (wall-extract scales by PX_TO_MM=38).
    Room/opening ids use bases wall-extract classifies on ('living', 'door', ...).
    Self-contained — no ResPlan dataset needed.
    """
    return [
        {"id": "living_0", "points": [[0, 0], [100, 0], [100, 80], [0, 80]]},
        {"id": "bedroom_0", "points": [[100, 0], [180, 0], [180, 80], [100, 80]]},
        {"id": "door_0", "points": [[96, 30], [104, 30], [104, 50], [96, 50]]},
        {"id": "window_0", "points": [[176, 30], [184, 30], [184, 50], [176, 50]]},
    ]
