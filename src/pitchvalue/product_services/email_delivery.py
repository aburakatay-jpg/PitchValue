"""Provider-neutral email delivery implementation using Resend."""

from __future__ import annotations

import httpx

from pitchvalue.config import load_settings


class ResendEmailVerificationDelivery:
    """Delivers verification emails via Resend HTTP API."""

    def __init__(self) -> None:
        self.settings = load_settings()

    def request_verification(self, normalized_email: str, raw_token: str) -> None:
        """Attempt to send a verification email."""
        if not self.settings.resend_api_key:
            raise RuntimeError("RESEND_API_KEY is not configured")
        if not self.settings.auth_email_from:
            raise RuntimeError("AUTH_EMAIL_FROM is not configured")
        if not self.settings.auth_verification_public_base_url:
            raise RuntimeError("AUTH_VERIFICATION_PUBLIC_BASE_URL is not configured")

        url = f"{self.settings.resend_api_base_url.rstrip('/')}/emails"
        headers = {
            "Authorization": f"Bearer {self.settings.resend_api_key}",
            "Content-Type": "application/json",
        }

        verification_url = (
            f"{self.settings.auth_verification_public_base_url.rstrip('/')}/{raw_token}"
        )

        payload = {
            "from": self.settings.auth_email_from,
            "to": [normalized_email],
            "subject": "Doğrulama bağlantınız / Your verification link - PitchValue",
            "html": f"""
            <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto;">
                <h2>PitchValue</h2>
                <p>Hesabınızı doğrulamak için aşağıdaki bağlantıya tıklayın:</p>
                <p>Please click the link below to verify your account:</p>
                <p>
                    <a href="{verification_url}" style="display: inline-block; padding: 10px 20px; background-color: #007bff; color: white; text-decoration: none; border-radius: 5px;">
                        Doğrula / Verify
                    </a>
                </p>
                <p>Bu bağlantı 24 saat geçerlidir. (This link expires in 24 hours.)</p>
                <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;" />
                <p style="font-size: 12px; color: #666;">
                    Bu e-postayı siz talep etmediyseniz, lütfen dikkate almayın.
                    (If you didn't request this email, please ignore it.)
                </p>
            </div>
            """,
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise RuntimeError(
                f"Resend delivery failed with status {error.response.status_code}"
            ) from error
        except httpx.RequestError as error:
            raise RuntimeError("Resend delivery failed due to network error") from error
