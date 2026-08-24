"""Generate a PBKDF2 access-code hash suitable for DEMO_ACCESS_CODE_HASH."""

import base64
import getpass
import hashlib
import secrets


def main() -> None:
    code = getpass.getpass("Access code: ")
    if len(code) < 8:
        raise SystemExit("Use at least 8 characters.")
    iterations = 310_000
    salt = secrets.token_urlsafe(16)
    digest = hashlib.pbkdf2_hmac("sha256", code.encode(), salt.encode(), iterations)
    encoded = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    print(f"pbkdf2_sha256${iterations}${salt}${encoded}")


if __name__ == "__main__":
    main()
