"""
ImageShrink Pro V2 Google Sign-In Integration Service.
Separate OAuth 2.0 implementation strictly for user authentication (OpenID Connect).
Scopes: openid, email, profile.
Distinct from Gmail API email delivery service.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.parse
import urllib.request
import uuid
from typing import Any, Dict, Optional, Tuple

from app.config import settings

logger = logging.getLogger("imageshrink.google_signin")

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


class GoogleOAuthService:
    def __init__(self):
        self.client_id = settings.GOOGLE_AUTH_CLIENT_ID
        self.client_secret = settings.GOOGLE_AUTH_CLIENT_SECRET
        self.redirect_uri = settings.GOOGLE_AUTH_REDIRECT_URI

    def is_configured(self) -> bool:
        """Returns True if Google Sign-In client ID and secret are configured."""
        return bool(self.client_id and self.client_secret)

    def generate_authorization_url(self, state: Optional[str] = None) -> Tuple[str, str]:
        """
        Generates Google OAuth 2.0 authorization URL for user login.
        Returns: (authorization_url, state)
        """
        if not state:
            state = uuid.uuid4().hex

        params = {
            "client_id": self.client_id or "mock_client_id",
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "access_type": "online",
            "state": state,
            "prompt": "select_account",
        }
        url = f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"
        return url, state

    def exchange_code_for_user_info(self, code: str) -> Optional[Dict[str, Any]]:
        """
        Exchanges authorization code for tokens and queries OpenID userinfo endpoint.
        Returns dict with: sub (Google ID), email, name, picture, email_verified.
        """
        if not self.is_configured():
            logger.warning("Google Sign-In is not configured with credentials.")
            return None

        try:
            # 1. Exchange code for access token
            data = urllib.parse.urlencode({
                "code": code,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": self.redirect_uri,
                "grant_type": "authorization_code",
            }).encode("utf-8")

            req = urllib.request.Request(
                GOOGLE_TOKEN_URL,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                token_data = json.loads(resp.read().decode("utf-8"))

            access_token = token_data.get("access_token")
            if not access_token:
                logger.error("No access token returned from Google token exchange.")
                return None

            # 2. Fetch User Profile
            req_info = urllib.request.Request(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                method="GET"
            )
            with urllib.request.urlopen(req_info, timeout=10) as resp_info:
                user_info = json.loads(resp_info.read().decode("utf-8"))

            return {
                "google_id": user_info.get("sub"),
                "email": user_info.get("email"),
                "full_name": user_info.get("name") or user_info.get("email", "").split("@")[0],
                "email_verified": bool(user_info.get("email_verified", True)),
                "picture": user_info.get("picture"),
            }

        except Exception as e:
            logger.error(f"Failed to exchange Google OAuth code: {e}")
            return None


google_oauth_service = GoogleOAuthService()

