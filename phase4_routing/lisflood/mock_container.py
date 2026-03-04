"""
mock_container.py — Mock LISFLOOD-FP processing container.

Generates synthetic flood depth + velocity rasters (numpy arrays saved as
.npy) to the SageMaker Processing output directory.  When the real
LISFLOOD-FP model becomes available, replace **only this file**; every
other component (SageMaker job config, Lambda, PostGIS) remains unchanged.

SageMaker Processing directory conventions
------------------------------------------
  /opt/ml/processing/input/   — DEM, rainfall, boundary conditions
  /opt/ml/processing/output/  — flood depth & velocity rasters
"""

import json
import logging
import os
from datetime import datetime, timezone

import numpy as np

logger = logging.getLogger(__name__)

# SageMaker Processing conventions
DEFAULT_INPUT_DIR = "/opt/ml/processing/input"
DEFAULT_OUTPUT_DIR = "/opt/ml/processing/output"

# Raster dimensions (100 × 100 grid ≈ 10 km² at 100 m resolution)
GRID_ROWS = 100
GRID_COLS = 100

# Chennai bounding box (default study area)
BBOX = {
    "min_lat": 12.90,
    "max_lat": 13.20,
    "min_lon": 80.15,
    "max_lon": 80.35,
}


def generate_mock_depth_raster(
    rows: int = GRID_ROWS,
    cols: int = GRID_COLS,
    seed: int | None = None,
) -> np.ndarray:
    """
    Generate a synthetic flood-depth raster.

    Creates a 2D numpy array simulating a river-channel flood pattern:
    a Gaussian ridge along the centre with random noise to mimic
    terrain variation.

    Args:
        rows: Number of grid rows.
        cols: Number of grid columns.
        seed: Optional RNG seed for reproducibility.

    Returns:
        2D float32 array with depth values in metres (0 – ~3 m).
    """
    rng = np.random.default_rng(seed)

    # Gaussian flood channel along the centre column
    x = np.linspace(-3, 3, cols)
    y = np.linspace(-3, 3, rows)
    xx, yy = np.meshgrid(x, y)

    # River channel + spread
    depth = 2.5 * np.exp(-0.5 * (xx ** 2 + (yy - 0.5) ** 2))

    # Add realistic noise
    depth += rng.normal(0, 0.15, size=(rows, cols))

    # Clamp to non-negative
    depth = np.clip(depth, 0, None).astype(np.float32)

    return depth


def generate_mock_velocity_raster(
    depth: np.ndarray,
    seed: int | None = None,
) -> np.ndarray:
    """
    Generate a synthetic velocity raster correlated with depth.

    Simple model: velocity ∝ sqrt(depth) + noise, consistent with
    Manning's equation approximation.

    Args:
        depth: Corresponding depth raster.
        seed: Optional RNG seed.

    Returns:
        2D float32 array with velocity values in m/s.
    """
    rng = np.random.default_rng(seed)
    velocity = 0.8 * np.sqrt(depth) + rng.normal(0, 0.05, size=depth.shape)
    velocity = np.clip(velocity, 0, None).astype(np.float32)
    return velocity


def write_metadata(output_dir: str, depth: np.ndarray) -> dict:
    """Write simulation metadata JSON alongside rasters."""
    metadata = {
        "simulation_id": f"mock-lisflood-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "model": "mock-lisflood-fp",
        "grid_shape": list(depth.shape),
        "bbox": BBOX,
        "resolution_m": 100,
        "crs": "EPSG:4326",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "units": {"depth": "metres", "velocity": "m/s"},
    }
    meta_path = os.path.join(output_dir, "metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    logger.info("Metadata written to %s", meta_path)
    return metadata


def run_mock_simulation(
    input_dir: str = DEFAULT_INPUT_DIR,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    seed: int | None = 42,
) -> dict:
    """
    Execute the mock LISFLOOD-FP simulation.

    Reads nothing from ``input_dir`` (real model would read DEM +
    rainfall).  Writes depth + velocity .npy rasters and a metadata
    JSON to ``output_dir``.

    Args:
        input_dir:  SageMaker input channel path (unused in mock).
        output_dir: SageMaker output channel path.
        seed:       RNG seed for reproducible output.

    Returns:
        Dict with output paths and metadata.
    """
    os.makedirs(output_dir, exist_ok=True)
    logger.info("Mock LISFLOOD simulation starting (seed=%s)", seed)

    # Generate rasters
    depth = generate_mock_depth_raster(seed=seed)
    velocity = generate_mock_velocity_raster(depth, seed=seed)

    # Save rasters
    depth_path = os.path.join(output_dir, "flood_depth.npy")
    velocity_path = os.path.join(output_dir, "flood_velocity.npy")
    np.save(depth_path, depth)
    np.save(velocity_path, velocity)
    logger.info("Depth raster saved: %s  shape=%s", depth_path, depth.shape)
    logger.info("Velocity raster saved: %s  shape=%s", velocity_path, velocity.shape)

    # Write metadata
    metadata = write_metadata(output_dir, depth)

    logger.info("Mock LISFLOOD simulation complete")
    return {
        "depth_path": depth_path,
        "velocity_path": velocity_path,
        "metadata": metadata,
    }


# ── Entrypoint for SageMaker container ──────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    run_mock_simulation()
