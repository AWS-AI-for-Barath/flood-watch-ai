# Phase 4 to Phase 5 EventBridge Trigger

To string Phase 4 (Prediction) and Phase 5 (Alerting) together, we use an EventBridge rule.

## Architecture

When Phase 4 completes a routing/simulation task, it emits a custom event to the `default` event bus. The EventBridge rule matches this event and triggers the `processFloodAlerts` Lambda function, passing the predicted flood polygons in the payload.

## Create the Rule

1. Open **Amazon EventBridge** console.
2. Select **Rules** -> **Create rule**.
3. Name: `phase4_simulation_completed`
4. Event bus: `default`
5. Rule type: `Rule with an event pattern` -> Next
6. Event source: `Other`
7. Event pattern:
   ```json
   {
     "source": ["floodwatch.phase4"],
     "detail-type": ["phase4_simulation_completed"]
   }
   ```
8. Click **Next**.
9. Target 1: **AWS service**
10. Select **Lambda function**
11. Function: `processFloodAlerts`
12. Click **Next**, **Next**, **Create rule**.

## Testing

You can use the EventBridge **Send events** tool in the console with this payload:

**Event Source:** `floodwatch.phase4`
**Detail Type:** `phase4_simulation_completed`
**Detail:**
```json
{
  "flood_polygons": {
    "type": "FeatureCollection",
    "features": [
      {
        "type": "Feature",
        "geometry": {
          "type": "Polygon",
          "coordinates": [[[80.2600, 13.0700], [80.2800, 13.0700], [80.2800, 13.0900], [80.2600, 13.0900], [80.2600, 13.0700]]]
        },
        "properties": {
          "submergence_ratio": 0.5,
          "severity": "danger",
          "zone_id": "zone_123"
        }
      }
    ]
  }
}
```

Check the CloudWatch Logs for the `processFloodAlerts` Lambda to verify it received the event and triggered the dispatch simulation.
