import json
import os
import boto3

s3 = boto3.client('s3')
BUCKET = os.environ.get('BUCKET_NAME', 'floodwatch-uploads')
ALLOWED_ORIGINS = os.environ.get('ALLOWED_ORIGINS', '*')


def handler(event, context):
    """
    Generate pre-signed PUT URLs for media and metadata uploads.

    Request body:
    {
        "mediaKey": "media/<uuid>.<ext>",
        "metadataKey": "metadata/<uuid>.json"
    }

    Response:
    {
        "url": "<pre-signed media PUT URL>",
        "metadataUrl": "<pre-signed metadata PUT URL>"
    }
    """
    # Handle CORS preflight
    if event.get('requestContext', {}).get('http', {}).get('method') == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': _cors_headers(),
            'body': ''
        }

    try:
        body = json.loads(event.get('body', '{}'))
        media_key = body.get('mediaKey', '')
        metadata_key = body.get('metadataKey', '')

        if not media_key or not metadata_key:
            return {
                'statusCode': 400,
                'headers': _cors_headers(),
                'body': json.dumps({'error': 'mediaKey and metadataKey are required'})
            }

        # Validate key prefixes
        if not media_key.startswith('media/'):
            return {
                'statusCode': 400,
                'headers': _cors_headers(),
                'body': json.dumps({'error': 'mediaKey must start with media/'})
            }

        if not metadata_key.startswith('metadata/'):
            return {
                'statusCode': 400,
                'headers': _cors_headers(),
                'body': json.dumps({'error': 'metadataKey must start with metadata/'})
            }

        # Determine content type from extension
        if media_key.endswith('.mp4'):
            media_content_type = 'video/mp4'
        elif media_key.endswith('.jpg') or media_key.endswith('.jpeg'):
            media_content_type = 'image/jpeg'
        elif media_key.endswith('.webm'):
            media_content_type = 'video/webm'
        else:
            media_content_type = 'application/octet-stream'

        # Generate pre-signed URLs (5 min expiry)
        media_url = s3.generate_presigned_url('put_object', Params={
            'Bucket': BUCKET,
            'Key': media_key,
            'ContentType': media_content_type
        }, ExpiresIn=300)

        metadata_url = s3.generate_presigned_url('put_object', Params={
            'Bucket': BUCKET,
            'Key': metadata_key,
            'ContentType': 'application/json'
        }, ExpiresIn=300)

        return {
            'statusCode': 200,
            'headers': _cors_headers(),
            'body': json.dumps({
                'url': media_url,
                'metadataUrl': metadata_url
            })
        }

    except Exception as e:
        print(f'Error: {e}')
        return {
            'statusCode': 500,
            'headers': _cors_headers(),
            'body': json.dumps({'error': 'Internal server error'})
        }


def _cors_headers():
    return {
        'Access-Control-Allow-Origin': ALLOWED_ORIGINS,
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Content-Type': 'application/json'
    }
