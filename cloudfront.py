import logging
from datetime import datetime, timedelta, timezone

from botocore.signers import CloudFrontSigner
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key

from config import CLOUDFRONT_DOMAIN, CLOUDFRONT_KEY_ID, CLOUDFRONT_PRIVATE_KEY_PATH

logger = logging.getLogger("radio.cloudfront")

# Load private key once at module load
_private_key = None


def _get_private_key():
    global _private_key
    if _private_key is None:
        with open(CLOUDFRONT_PRIVATE_KEY_PATH, "rb") as f:
            _private_key = load_pem_private_key(f.read(), password=None)
        logger.info("Loaded CloudFront private key")
    return _private_key


def _rsa_signer(message: bytes) -> bytes:
    """RSA signer function for CloudFrontSigner."""
    key = _get_private_key()
    return key.sign(message, padding.PKCS1v15(), hashes.SHA1())


def get_signed_url(filename: str, expires_days: int = 3) -> str:
    """
    Generate a CloudFront signed URL for an audio file.

    Args:
        filename: The audio filename (e.g., "haunting_tavern_remst_fullmix.mp3")
        expires_days: URL validity in days (default: 3)

    Returns:
        Signed CloudFront URL
    """
    url = f"https://{CLOUDFRONT_DOMAIN}/audio/{filename}"
    expires = datetime.now(timezone.utc) + timedelta(days=expires_days)

    signer = CloudFrontSigner(CLOUDFRONT_KEY_ID, _rsa_signer)
    signed_url = signer.generate_presigned_url(url, date_less_than=expires)

    return signed_url
