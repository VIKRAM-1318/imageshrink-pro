"""
ImageShrink Pro V2 Transactional Email Templates.
Provides responsive, accessible, professionally branded HTML and plain-text email templates for:
1. Account Registration Confirmation
2. Email Verification (Action link + 6-Digit OTP code)
3. Email Verification Reminder
4. Password Reset Request
5. Password Change Confirmation
6. Email Address Change Notification
7. New Device Login Notification
8. Suspicious Login Alert
9. Account Deletion Confirmation
10. Security Alert
"""
from __future__ import annotations

import html
from typing import Any, Dict, Optional, Tuple


def _render_base_email(
    title: str,
    preheader: str,
    heading: str,
    body_html: str,
    call_to_action: Optional[Dict[str, str]] = None,
    warning_box: Optional[str] = None,
    meta_info: Optional[Dict[str, str]] = None,
    app_base_url: str = "http://localhost:8000",
) -> str:
    """Renders the master responsive HTML layout with ImageShrink Pro dark-slate branding."""
    cta_html = ""
    if call_to_action:
        url = html.escape(call_to_action.get("url", "#"))
        text = html.escape(call_to_action.get("text", "Continue"))
        cta_html = f"""
        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="margin: 28px 0;">
          <tr>
            <td align="center">
              <a href="{url}" target="_blank" style="display: inline-block; padding: 14px 32px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 15px; font-weight: 700; color: #ffffff; text-decoration: none; background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%); border-radius: 12px; box-shadow: 0 4px 14px rgba(79, 70, 229, 0.4); text-align: center; letter-spacing: 0.2px;">
                {text} &rarr;
              </a>
            </td>
          </tr>
        </table>
        """

    warning_html = ""
    if warning_box:
        warning_html = f"""
        <div style="background-color: #27272a; border-left: 4px solid #f59e0b; padding: 14px 18px; border-radius: 8px; margin: 20px 0; color: #d4d4d8; font-size: 13px; line-height: 1.5;">
          <strong style="color: #fbbf24;">Security Notice:</strong> {html.escape(warning_box)}
        </div>
        """

    meta_html = ""
    if meta_info:
        rows = "".join(
            f"<tr><td style='padding: 6px 12px 6px 0; color: #a1a1aa; font-size: 12px; font-weight: 600;'>{html.escape(k)}:</td><td style='padding: 6px 0; color: #f4f4f5; font-size: 12px; font-family: monospace;'>{html.escape(str(v))}</td></tr>"
            for k, v in meta_info.items()
        )
        meta_html = f"""
        <div style="background-color: #18181b; border: 1px solid #27272a; border-radius: 10px; padding: 16px; margin: 20px 0;">
          <table border="0" cellpadding="0" cellspacing="0" width="100%">{rows}</table>
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(title)}</title>
  <style>
    body {{ margin: 0; padding: 0; background-color: #09090b; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased; }}
    table {{ border-collapse: collapse; }}
    @media only screen and (max-width: 600px) {{
      .wrapper {{ width: 100% !important; padding: 16px !important; }}
      .card {{ padding: 24px !important; }}
    }}
  </style>
</head>
<body style="margin: 0; padding: 0; background-color: #09090b; color: #f4f4f5;">
  <span style="display: none; font-size: 1px; color: #09090b; max-height: 0; opacity: 0; overflow: hidden; mso-hide: all;">
    {html.escape(preheader)}
  </span>
  <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #09090b; padding: 40px 10px;">
    <tr>
      <td align="center">
        <!-- Container -->
        <table border="0" cellpadding="0" cellspacing="0" width="560" class="wrapper" style="width: 560px; max-width: 100%;">
          <!-- Brand Header -->
          <tr>
            <td align="center" style="padding-bottom: 24px;">
              <a href="{app_base_url}" style="text-decoration: none; display: inline-flex; align-items: center; gap: 8px;">
                <span style="display: inline-block; width: 34px; height: 34px; background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%); border-radius: 9px; vertical-align: middle; line-height: 34px; text-align: center; color: #ffffff; font-weight: 900; font-size: 18px;">IS</span>
                <span style="font-size: 20px; font-weight: 800; color: #ffffff; vertical-align: middle; letter-spacing: -0.5px; margin-left: 8px;">ImageShrink <span style="color: #818cf8;">Pro</span></span>
              </a>
            </td>
          </tr>
          <!-- Main Card -->
          <tr>
            <td class="card" style="background-color: #121215; border: 1px solid #27272a; border-radius: 18px; padding: 36px 36px; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.45);">
              <h1 style="margin: 0 0 16px 0; font-size: 22px; font-weight: 800; color: #ffffff; letter-spacing: -0.3px;">
                {html.escape(heading)}
              </h1>
              <div style="font-size: 14px; line-height: 1.65; color: #a1a1aa;">
                {body_html}
              </div>
              {meta_html}
              {cta_html}
              {warning_html}
              <div style="margin-top: 28px; padding-top: 20px; border-top: 1px solid #27272a; font-size: 12px; color: #71717a; line-height: 1.5;">
                If you did not make this request or have security questions, please contact our security team immediately or reset your credentials.
              </div>
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td align="center" style="padding-top: 24px; font-size: 11px; color: #52525b; line-height: 1.6;">
              <p style="margin: 0 0 4px 0;">&copy; 2026 ImageShrink Pro SaaS. All rights reserved.</p>
              <p style="margin: 0;">Sent securely via Google Workspace &bull; <a href="{app_base_url}/privacy" style="color: #818cf8; text-decoration: none;">Privacy Policy</a> &bull; <a href="{app_base_url}/terms" style="color: #818cf8; text-decoration: none;">Terms of Service</a></p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


class EmailTemplates:
    @staticmethod
    def account_registration(full_name: str, email: str, app_base_url: str = "http://localhost:8000") -> Tuple[str, str, str]:
        """Welcome email upon initial account creation."""
        name = full_name or email.split("@")[0]
        subject = "Welcome to ImageShrink Pro! Your Account is Ready"
        preheader = "Welcome to ImageShrink Pro! Your free tier is now active."
        body_html = f"""
        <p>Hello <strong>{html.escape(name)}</strong>,</p>
        <p>Thank you for creating an account with <strong>ImageShrink Pro</strong>. Your intelligent bulk image optimization platform is ready.</p>
        <p>Your account is initialized on our <strong>Free Plan</strong> with <strong>50 monthly processing credits</strong>, supporting lossless and visually-lossless optimization for JPG, JPEG, and PNG formats.</p>
        <p>Please check your inbox for an email verification link to verify your identity and unlock complete batch studio features.</p>
        """
        html_content = _render_base_email(
            title="Welcome to ImageShrink Pro",
            preheader=preheader,
            heading="Welcome to ImageShrink Pro",
            body_html=body_html,
            call_to_action={"url": f"{app_base_url}#workspace", "text": "Open Studio Workspace"},
            app_base_url=app_base_url,
        )
        text_content = f"Hello {name},\n\nWelcome to ImageShrink Pro! Your free account has been registered with email {email}.\nOpen your studio workspace: {app_base_url}#workspace\n\nImageShrink Pro Team"
        return subject, html_content, text_content

    @staticmethod
    def email_verification(full_name: str, email: str, verify_url: str, otp_code: str, app_base_url: str = "http://localhost:8000") -> Tuple[str, str, str]:
        """Verification email containing token link and 6-digit OTP code."""
        name = full_name or email.split("@")[0]
        subject = f"Verify your email address - ImageShrink Pro (OTP: {otp_code})"
        preheader = f"Your verification code is {otp_code}. Complete your email verification."
        body_html = f"""
        <p>Hello <strong>{html.escape(name)}</strong>,</p>
        <p>Please verify your email address to confirm your account and enable full SaaS features.</p>
        <div style="background-color: #1e1b4b; border: 1px solid #4338ca; border-radius: 12px; padding: 20px; text-align: center; margin: 24px 0;">
          <span style="font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 1.5px; color: #a5b4fc; display: block; margin-bottom: 8px;">Six-Digit Verification Code</span>
          <span style="font-family: 'SF Mono', Consolas, Monaco, monospace; font-size: 32px; font-weight: 900; letter-spacing: 6px; color: #ffffff;">{otp_code}</span>
          <span style="font-size: 11px; color: #818cf8; display: block; margin-top: 6px;">Valid for 24 hours &bull; Single-use only</span>
        </div>
        <p>You can enter this 6-digit code in the app, or click the button below to verify instantly:</p>
        """
        html_content = _render_base_email(
            title="Verify Your Email Address",
            preheader=preheader,
            heading="Verify Your Email Address",
            body_html=body_html,
            call_to_action={"url": verify_url, "text": "Verify Email Address Now"},
            warning_box="This verification link and code will expire in 24 hours. Never share this code with anyone.",
            app_base_url=app_base_url,
        )
        text_content = f"Hello {name},\n\nPlease verify your email address.\nYour 6-digit OTP code: {otp_code}\nOr verify instantly by clicking:\n{verify_url}\n\nValid for 24 hours.\n\nImageShrink Pro Team"
        return subject, html_content, text_content

    @staticmethod
    def verification_reminder(full_name: str, email: str, verify_url: str, otp_code: str, app_base_url: str = "http://localhost:8000") -> Tuple[str, str, str]:
        """Reminder to verify email address."""
        name = full_name or email.split("@")[0]
        subject = "Reminder: Please verify your ImageShrink Pro email address"
        preheader = "Your ImageShrink Pro account is waiting to be verified."
        body_html = f"""
        <p>Hello <strong>{html.escape(name)}</strong>,</p>
        <p>We noticed you haven't verified your email address (<strong>{html.escape(email)}</strong>) yet.</p>
        <p>Verifying your email ensures account recovery is always accessible and protects your image optimization quotas.</p>
        <div style="background-color: #1e1b4b; border: 1px solid #4338ca; border-radius: 12px; padding: 16px; text-align: center; margin: 20px 0;">
          <span style="font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 1.5px; color: #a5b4fc; display: block; margin-bottom: 4px;">Verification OTP</span>
          <span style="font-family: monospace; font-size: 26px; font-weight: 800; letter-spacing: 5px; color: #ffffff;">{otp_code}</span>
        </div>
        """
        html_content = _render_base_email(
            title="Email Verification Reminder",
            preheader=preheader,
            heading="Complete Your Email Verification",
            body_html=body_html,
            call_to_action={"url": verify_url, "text": "Verify My Account"},
            app_base_url=app_base_url,
        )
        text_content = f"Hello {name},\n\nReminder: Please verify your email for ImageShrink Pro.\nOTP: {otp_code}\nLink: {verify_url}\n\nImageShrink Pro Team"
        return subject, html_content, text_content

    @staticmethod
    def password_reset(full_name: str, email: str, reset_url: str, app_base_url: str = "http://localhost:8000") -> Tuple[str, str, str]:
        """Password reset link email."""
        name = full_name or email.split("@")[0]
        subject = "Reset your ImageShrink Pro password"
        preheader = "A request was received to reset your password. Valid for 1 hour."
        body_html = f"""
        <p>Hello <strong>{html.escape(name)}</strong>,</p>
        <p>We received a request to reset the password for your ImageShrink Pro account (<strong>{html.escape(email)}</strong>).</p>
        <p>Click the button below to set a new password. This link is single-use and will expire in <strong>1 hour</strong>.</p>
        """
        html_content = _render_base_email(
            title="Reset Your Password",
            preheader=preheader,
            heading="Password Reset Request",
            body_html=body_html,
            call_to_action={"url": reset_url, "text": "Reset My Password"},
            warning_box="If you did not request this password reset, you can safely ignore this email. Your password will remain unchanged.",
            app_base_url=app_base_url,
        )
        text_content = f"Hello {name},\n\nA password reset was requested for {email}.\nReset link (valid 1 hour):\n{reset_url}\n\nIf you did not request this, please ignore this email.\n\nImageShrink Pro Team"
        return subject, html_content, text_content

    @staticmethod
    def password_changed(full_name: str, email: str, ip_address: str, user_agent: str, timestamp_str: str, app_base_url: str = "http://localhost:8000") -> Tuple[str, str, str]:
        """Notification sent when account password has been successfully changed."""
        name = full_name or email.split("@")[0]
        subject = "Security Alert: Your ImageShrink Pro password was changed"
        preheader = "Your ImageShrink Pro account password has been successfully changed."
        body_html = f"""
        <p>Hello <strong>{html.escape(name)}</strong>,</p>
        <p>This is a confirmation that the password for your account (<strong>{html.escape(email)}</strong>) was recently changed.</p>
        <p>All previous sessions on other devices have been automatically invalidated for your protection.</p>
        """
        meta = {
            "Timestamp": timestamp_str,
            "IP Address": ip_address or "Unknown",
            "Device / Browser": user_agent or "Web Client",
        }
        html_content = _render_base_email(
            title="Password Changed Confirmation",
            preheader=preheader,
            heading="Password Successfully Changed",
            body_html=body_html,
            meta_info=meta,
            warning_box="If you did not perform this change, your account may be compromised. Please reset your password immediately.",
            app_base_url=app_base_url,
        )
        text_content = f"Hello {name},\n\nYour ImageShrink Pro password was changed on {timestamp_str} from IP {ip_address}.\nIf you did not perform this action, contact support immediately.\n\nImageShrink Pro Team"
        return subject, html_content, text_content

    @staticmethod
    def email_change_verification(full_name: str, new_email: str, verify_url: str, app_base_url: str = "http://localhost:8000") -> Tuple[str, str, str]:
        """Verification email sent to a newly requested email address."""
        name = full_name or new_email.split("@")[0]
        subject = "Verify your new email address - ImageShrink Pro"
        preheader = "Confirm this new email address to update your account."
        body_html = f"""
        <p>Hello <strong>{html.escape(name)}</strong>,</p>
        <p>A request was submitted to change your ImageShrink Pro account login to this email address (<strong>{html.escape(new_email)}</strong>).</p>
        <p>Please click the button below to verify this address and complete the update.</p>
        """
        html_content = _render_base_email(
            title="Verify New Email Address",
            preheader=preheader,
            heading="Confirm Email Address Change",
            body_html=body_html,
            call_to_action={"url": verify_url, "text": "Confirm & Update Email"},
            warning_box="If you did not request this email change, do not click the link above.",
            app_base_url=app_base_url,
        )
        text_content = f"Hello {name},\n\nPlease confirm your new email address for ImageShrink Pro by visiting:\n{verify_url}\n\nImageShrink Pro Team"
        return subject, html_content, text_content

    @staticmethod
    def new_device_login(full_name: str, email: str, ip_address: str, user_agent: str, timestamp_str: str, app_base_url: str = "http://localhost:8000") -> Tuple[str, str, str]:
        """Alert sent when account is accessed from an unrecognized browser or IP."""
        name = full_name or email.split("@")[0]
        subject = "New sign-in detected on ImageShrink Pro"
        preheader = f"New sign-in from {ip_address}. Was this you?"
        body_html = f"""
        <p>Hello <strong>{html.escape(name)}</strong>,</p>
        <p>Your ImageShrink Pro account was signed in to from a new device or browser.</p>
        """
        meta = {
            "Timestamp": timestamp_str,
            "IP Address": ip_address or "Unknown",
            "Browser / Client": user_agent or "Web Client",
        }
        html_content = _render_base_email(
            title="New Sign-in Detected",
            preheader=preheader,
            heading="New Sign-In Detected",
            body_html=body_html,
            meta_info=meta,
            call_to_action={"url": f"{app_base_url}#dashboard", "text": "Review Account Sessions"},
            warning_box="If this was you, no action is needed. If you do not recognize this activity, change your password immediately and revoke active sessions.",
            app_base_url=app_base_url,
        )
        text_content = f"Hello {name},\n\nA new sign-in was detected on your ImageShrink Pro account on {timestamp_str} from {ip_address} ({user_agent}).\nReview your active sessions: {app_base_url}#dashboard\n\nImageShrink Pro Team"
        return subject, html_content, text_content

    @staticmethod
    def suspicious_login_alert(full_name: str, email: str, ip_address: str, reason: str, timestamp_str: str, app_base_url: str = "http://localhost:8000") -> Tuple[str, str, str]:
        """Alert sent upon suspicious authentication activity (e.g. repeated failed logins)."""
        name = full_name or email.split("@")[0]
        subject = "CRITICAL SECURITY ALERT: Suspicious activity on your account"
        preheader = "Repeated failed login attempts or unusual access detected."
        body_html = f"""
        <p>Hello <strong>{html.escape(name)}</strong>,</p>
        <p>Our automated security shield detected suspicious authentication activity attempting to access your account (<strong>{html.escape(email)}</strong>).</p>
        <p><strong>Reason:</strong> {html.escape(reason)}</p>
        """
        meta = {
            "Timestamp": timestamp_str,
            "Originating IP": ip_address or "Unknown",
            "Account Status": "Temporary Security Lock Applied",
        }
        html_content = _render_base_email(
            title="Suspicious Login Activity",
            preheader=preheader,
            heading="Suspicious Login Activity Detected",
            body_html=body_html,
            meta_info=meta,
            call_to_action={"url": f"{app_base_url}#reset-password", "text": "Secure Your Account Now"},
            warning_box="Your account was temporarily shielded. We strongly recommend resetting your password immediately.",
            app_base_url=app_base_url,
        )
        text_content = f"Hello {name},\n\nSuspicious login activity was detected on your account {email}.\nReason: {reason}\nIP: {ip_address}\nTimestamp: {timestamp_str}\nPlease reset your password: {app_base_url}#reset-password\n\nImageShrink Pro Security Team"
        return subject, html_content, text_content

    @staticmethod
    def account_deleted(full_name: str, email: str, timestamp_str: str, app_base_url: str = "http://localhost:8000") -> Tuple[str, str, str]:
        """Account deletion confirmation."""
        name = full_name or email.split("@")[0]
        subject = "Your ImageShrink Pro account has been deleted"
        preheader = "Confirmation that your account and personal data were removed."
        body_html = f"""
        <p>Hello <strong>{html.escape(name)}</strong>,</p>
        <p>This email confirms that your ImageShrink Pro account (<strong>{html.escape(email)}</strong>) and associated active subscriptions have been permanently deleted as requested.</p>
        <p>All active sessions have been terminated, and uploaded images have been scheduled for immediate storage purge.</p>
        <p>We're sorry to see you go. If you ever wish to use ImageShrink Pro again, you are welcome to create a new account anytime.</p>
        """
        html_content = _render_base_email(
            title="Account Deleted",
            preheader=preheader,
            heading="Account Successfully Deleted",
            body_html=body_html,
            app_base_url=app_base_url,
        )
        text_content = f"Hello {name},\n\nYour ImageShrink Pro account for {email} has been permanently deleted on {timestamp_str}.\nThank you for using ImageShrink Pro.\n\nImageShrink Pro Team"
        return subject, html_content, text_content

    @staticmethod
    def security_alert(full_name: str, email: str, alert_title: str, alert_message: str, app_base_url: str = "http://localhost:8000") -> Tuple[str, str, str]:
        """Important security alert notice."""
        name = full_name or email.split("@")[0]
        subject = f"Security Notice: {alert_title} - ImageShrink Pro"
        preheader = alert_title
        body_html = f"""
        <p>Hello <strong>{html.escape(name)}</strong>,</p>
        <p>{html.escape(alert_message)}</p>
        """
        html_content = _render_base_email(
            title="Important Security Notice",
            preheader=preheader,
            heading=alert_title,
            body_html=body_html,
            call_to_action={"url": f"{app_base_url}#dashboard", "text": "View Account Security"},
            app_base_url=app_base_url,
        )
        text_content = f"Hello {name},\n\nSecurity Notice: {alert_title}\n{alert_message}\n\nImageShrink Pro Team"
        return subject, html_content, text_content

