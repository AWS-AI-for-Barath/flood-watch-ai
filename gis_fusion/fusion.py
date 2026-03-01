def compute_water_level(elevation_m: float, depth_cm: float) -> float:
    """
    Compute total water level in meters.
    water_level_m = elevation_m + depth_cm / 100
    """
    return elevation_m + (depth_cm / 100.0)
