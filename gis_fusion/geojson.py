def generate_geojson(surface_points: list, severity: str) -> dict:
    """
    Generate GeoJSON polygon or multipoint from surface points.
    """
    coordinates = []
    
    for pt in surface_points:
        # GeoJSON is [lon, lat]
        coordinates.append([pt["lon"], pt["lat"]])
        
    # Using MultiPoint for simplicity, or we could construct a Polygon
    geojson = {
        "type": "Feature",
        "geometry": {
            "type": "MultiPoint",
            "coordinates": coordinates
        },
        "properties": {
            "severity": severity
        }
    }
    
    return geojson
