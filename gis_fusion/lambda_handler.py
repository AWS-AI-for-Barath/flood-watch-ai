import json
from .elevation import get_elevation
from .fusion import compute_water_level
from .interpolation import interpolate_surface
from .geojson import generate_geojson

def handler(event, context):
    """
    AWS Lambda handler for GIS Fusion layer.
    
    Step Functions Input:
    {
      "lat": float,
      "lon": float,
      "water_depth_cm": float,
      "severity": "low|medium|high"
    }
    
    Step Functions Output:
    {
      "geojson": {...},
      "water_level_m": float
    }
    """
    # 1. read lat, lon, depth
    lat = float(event.get("lat", 0.0))
    lon = float(event.get("lon", 0.0))
    depth_cm = float(event.get("water_depth_cm", 0.0))
    severity = event.get("severity", "low")
    
    # 2. get elevation
    elevation_m = get_elevation(lat, lon)
    
    # 3. compute water level
    water_level_m = compute_water_level(elevation_m, depth_cm)
    
    # 4. interpolate surface (simulate surface around the detection)
    points = [{"lat": lat, "lon": lon, "water_level": water_level_m}]
    surface_points = interpolate_surface(points)
    
    # 5. generate GeoJSON
    geojson_feature = generate_geojson(surface_points, severity)
    
    # 6. return JSON output for Step Functions
    return {
        "geojson": geojson_feature,
        "water_level_m": water_level_m
    }
