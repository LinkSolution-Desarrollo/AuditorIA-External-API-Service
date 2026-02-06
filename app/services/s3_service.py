import logging
import boto3
import os
from botocore.exceptions import NoCredentialsError


def get_s3_client():
    return boto3.client(
        's3',
        aws_access_key_id=os.getenv(
            'S3_ACCESS_KEY') or os.getenv('MINIO_ACCESS_KEY'),
        aws_secret_access_key=os.getenv(
            'S3_SECRET_KEY') or os.getenv('MINIO_SECRET_ACCESS_KEY'),
        endpoint_url=os.getenv('S3_ENDPOINT') or os.getenv('MINIO_URL')
    )


def upload_file_to_s3(file_path, bucket_name, object_name=None):
    """
    Upload a file to an S3 bucket

    :param file_path: File to upload
    :param bucket_name: Bucket to upload to
    :param object_name: S3 object name. If not specified then file_name is used
    :return: True if file was uploaded, else False
    """
    # If S3 object_name was not specified, use file_name
    if object_name is None:
        object_name = os.path.basename(file_path)

    # Determine content type
    import mimetypes
    content_type, _ = mimetypes.guess_type(file_path)
    if content_type is None:
        content_type = 'application/octet-stream'

    extra_args = {
        'ContentType': content_type,
        'CacheControl': 'public, max-age=31536000, immutable'
    }

    s3_client = get_s3_client()

    try:
        s3_client.upload_file(file_path, bucket_name,
                              object_name, ExtraArgs=extra_args)
    except FileNotFoundError:
        print("The file was not found")
        return False
    except NoCredentialsError:
        print("Credentials not available")
        return False
    except Exception as e:
        print(f"S3 Upload Error: {e}")
        return False
    return True


def create_folder_in_s3(bucket_name, folder_name):
    """
    Creates a 'folder' in S3 (which is just a zero-byte object with a trailing slash)
    """
    s3_client = get_s3_client()
    try:
        if not folder_name.endswith('/'):
            folder_name += '/'
        s3_client.put_object(Bucket=bucket_name, Key=folder_name)
    except Exception as e:
        print(f"S3 Create Folder Error: {e}")
        return False
    return True


logger = logging.getLogger(__name__)


def upload_fileobj_to_s3(file_obj, bucket_name, object_name, content_type=None):
    """
    Upload a file-like object to an S3 bucket
    """
    try:
        s3_client = get_s3_client()
        extra_args = {
            'CacheControl': 'public, max-age=31536000, immutable'
        }
        if content_type:
            extra_args['ContentType'] = content_type

        s3_client.upload_fileobj(
            file_obj, bucket_name, object_name, ExtraArgs=extra_args)
    except Exception as e:
        logger.error(f"S3 Upload Error: {e}")
        print(f"DEBUG: S3 Upload Error: {e}", flush=True)
        return False
    return True


def download_file_from_s3(bucket_name, object_name, file_path):
    """
    Download a file from an S3 bucket
    """
    s3_client = get_s3_client()
    try:
        s3_client.download_file(bucket_name, object_name, file_path)
    except Exception as e:
        logger.error(f"S3 Download Error: {e}")
        return False
    return True


def get_presigned_s3_client():
    """
    Get a Boto3 client configured for generating presigned URLs with the external endpoint.
    This ensures the signature matches the Host header sent by the browser.
    """
    import botocore.config

    # Use external endpoint (localhost:9000 for dev) or fallback to configured internal
    endpoint_url = os.getenv('S3_EXTERNAL_ENDPOINT', 'http://localhost:9000')

    return boto3.client(
        's3',
        aws_access_key_id=os.getenv(
            'S3_ACCESS_KEY') or os.getenv('MINIO_ACCESS_KEY'),
        aws_secret_access_key=os.getenv(
            'S3_SECRET_KEY') or os.getenv('MINIO_SECRET_ACCESS_KEY'),
        endpoint_url=endpoint_url,
        config=botocore.config.Config(signature_version='s3v4', s3={
                                      'addressing_style': 'path'})
    )


def create_presigned_url(bucket_name, object_name, expiration=3600):
    """
    Generate a presigned URL to share an S3 object with the correct external hostname and signature.

    :param bucket_name: string
    :param object_name: string
    :param expiration: Time in seconds for the presigned URL to remain valid
    :return: Presigned URL as string. If error, returns None.
    """
    import mimetypes
    try:
        # Use the specialized client that knows about the external hostname
        s3_client = get_presigned_s3_client()

        # Guess mime type to ensure browser plays it
        mime_type, _ = mimetypes.guess_type(object_name)
        if not mime_type:
            # Fallback for common audio formats if guessing fails
            if object_name.lower().endswith('.wav'):
                mime_type = 'audio/wav'
            elif object_name.lower().endswith('.mp3'):
                mime_type = 'audio/mpeg'
            elif object_name.lower().endswith('.ogg'):
                mime_type = 'audio/ogg'
            else:
                mime_type = 'application/octet-stream'

        params = {
            'Bucket': bucket_name,
            'Key': object_name,
            'ResponseContentType': mime_type
        }

        response = s3_client.generate_presigned_url(
            'get_object', Params=params, ExpiresIn=expiration)
    except Exception as e:
        logger.error(f"Error creating presigned URL: {e}")
        return None

    return response


def get_s3_object(bucket_name, object_name):
    """
    Get an object from an S3 bucket
    """
    s3_client = get_s3_client()
    try:
        response = s3_client.get_object(Bucket=bucket_name, Key=object_name)
        return response
    except Exception as e:
        logger.error(f"S3 Get Object Error: {e}")
        return None


def check_file_exists_in_s3(bucket_name, object_name):
    """
    Check if an object exists in an S3 bucket
    """
    s3_client = get_s3_client()
    try:
        s3_client.head_object(Bucket=bucket_name, Key=object_name)
        return True
    except Exception:
        return False
