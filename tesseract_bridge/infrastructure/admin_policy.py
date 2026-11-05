"""Administrative credential policy without Flask/runtime dependencies."""
import base64
import binascii
import os


def admin_token():
    encoded = os.environ.get('TESSERACT_BRIDGE_ADMIN_TOKEN_B64', '')
    if encoded:
        try:
            return base64.b64decode(encoded, validate=True).decode('utf-8')
        except (ValueError, UnicodeError, binascii.Error) as exc:
            raise ValueError('Invalid encoded administrative credential.') from exc
    return os.environ.get('TESSERACT_BRIDGE_ADMIN_TOKEN', '')


def local_admin_enabled():
    return os.environ.get('TESSERACT_BRIDGE_LOCAL_ADMIN', '').strip().lower() in ('1', 'true', 'yes', 'on')
