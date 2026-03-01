import json
from gis_fusion.lambda_handler import handler

def test_local():
    """
    Local test simulating AWS Lambda event for GIS Fusion.
    """
    event = {
        "lat": 12.93,
        "lon": 80.23,
        "water_depth_cm": 40.0,
        "severity": "high"
    }
    
    print("Simulating Step Functions Input:")
    print(json.dumps(event, indent=2))
    
    context = {}
    
    # Run handler
    result = handler(event, context)
    
    print("\n--- GIS Fusion Complete ---")
    print("\nStep Functions Output:")
    print(json.dumps(result, indent=2))
    
if __name__ == "__main__":
    test_local()
