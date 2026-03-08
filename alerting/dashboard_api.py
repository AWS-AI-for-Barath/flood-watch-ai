"""
dashboard_api.py -- Responder API endpoint for recent alerts.

Exposes a JSON endpoint to query the alert history from DynamoDB.
"""

import json
import logging
from .alert_history import get_recent_alerts

logger = logging.getLogger(__name__)

def lambda_handler(event, context):
    """
    API Gateway Lambda proxy handler for: GET /alerts/recent
    
    Query Parameters:
        limit (int): Number of recent alerts to return (default 50).
    """
    try:
        query_params = event.get("queryStringParameters") or {}
        limit_str = query_params.get("limit", "50")
        
        try:
            limit = int(limit_str)
            limit = min(max(1, limit), 100) # clamp 1-100
        except ValueError:
            limit = 50
            
        alerts = get_recent_alerts(limit=limit)
        
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({
                "status": "success",
                "count": len(alerts),
                "data": alerts
            })
        }
        
    except Exception as e:
        logger.error("Dashboard API error: %s", str(e), exc_info=True)
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "status": "error",
                "message": "Internal server error retrieving alerts."
            })
        }
