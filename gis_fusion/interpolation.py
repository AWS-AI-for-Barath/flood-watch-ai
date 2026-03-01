def interpolate_surface(points: list) -> list:
    """
    Convert multiple detections to flood surface using radius spread.
    
    Input:
    [
      {"lat": float, "lon": float, "water_level": float}
    ]
    
    Output:
    List of surface points forming a simple geometry around detections.
    """
    surface_points = []
    
    # Simple radius spread around each point (e.g., 4 points forming a small square/diamond)
    # 0.001 degrees is roughly 111 meters
    offset = 0.001
    
    for pt in points:
        lat = pt["lat"]
        lon = pt["lon"]
        level = pt["water_level"]
        
        # Add a simple spread around the detection point
        surface_points.extend([
            {"lat": lat + offset, "lon": lon, "water_level": level},
            {"lat": lat, "lon": lon + offset, "water_level": level},
            {"lat": lat - offset, "lon": lon, "water_level": level},
            {"lat": lat, "lon": lon - offset, "water_level": level}
        ])
        
    return surface_points
