"""Generate an authenticator setup key for the platform owner."""

from __future__ import annotations

from urllib.parse import quote

from app.web.platform_owner_totp import generate_base32_secret


def main() -> None:
    secret = generate_base32_secret()
    label = quote("Mentor Connect:Platform Owner")
    issuer = quote("Mentor Connect")
    print("PLATFORM_OWNER_MFA_SETUP")
    print(f"setup_key={secret}")
    print(
        "authenticator_uri="
        f"otpauth://totp/{label}?secret={secret}&issuer={issuer}&digits=6&period=30"
    )
    print("Store the setup key as INTERTOP_PLATFORM_OWNER_TOTP_SECRET on the server.")


if __name__ == "__main__":
    main()
