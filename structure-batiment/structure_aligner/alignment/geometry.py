from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from structure_aligner.config import Thread


def euclidean_displacement(x1: float, y1: float, z1: float,
                           x2: float, y2: float, z2: float) -> float:
    """Calculate 3D Euclidean distance between two points (for reporting)."""
    return math.sqrt((x2 - x1)**2 + (y2 - y1)**2 + (z2 - z1)**2)


def find_matching_thread(coord: float, threads: list[Thread], alpha: float) -> Thread | None:
    """
    Find the closest thread whose reference is within alpha of the coordinate.

    Unlike the original plan, this:
    - Matches within alpha of the thread reference (not within delta)
    - Returns the CLOSEST thread when multiple threads match (deterministic)

    Args:
        coord: The coordinate value to match.
        threads: List of Thread objects for this axis.
        alpha: Maximum allowed per-axis displacement.

    Returns:
        The closest matching Thread, or None if no thread matches.
    """
    best_thread = None
    best_displacement = float("inf")

    for thread in threads:
        displacement = abs(coord - thread.reference)
        if displacement <= alpha and displacement < best_displacement:
            best_thread = thread
            best_displacement = displacement

    return best_thread
