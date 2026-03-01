def get_elevation(lat: float, lon: float) -> float:
    """
    Mock terrain elevation lookup.
    Returns deterministic elevation in meters based on coordinates.
    """
    # Simple deterministic mock elevation between 5 and 15 meters
    # Using modulo and a basic hash-like sum to keep it deterministic
    base_elevation = 5.0
    variation = ((abs(lat) * 100) + (abs(lon) * 100)) % 10.0
    return base_elevation + variation
