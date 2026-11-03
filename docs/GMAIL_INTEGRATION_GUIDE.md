# ImageShrink Pro V2 - Google Gmail / Google Workspace Transactional Email Guide

This document provides complete instructions for configuring, securing, and maintaining the **Google Gmail API** and **Google Sign-In** integrations for ImageShrink Pro V2.

---

## 1. Google Cloud Console Setup

### Step 1.1: Create or Select a Google Cloud Project
1. Navigate to the [Google Cloud Console](https://console.cloud.google.com/).
2. Click **Select a project** > **New Project**.
3. Name your project (e.g., `ImageShrink-Pro-Production`).
4. Click **Create**.

### Step 1.2: Enable the Gmail API
1. In the left navigation menu, go to **APIs & Services** > **Library**.
2. Search for `Gmail API`.
3. Select **Gmail API** and click **Enable**.

---

## 2. OAuth Consent Screen Configuration

1. In **APIs & Services**, select **OAuth consent screen**.
2. Select **User Type**:
   * **Internal**: If your Google Workspace account handles all sending internally within your organization.
   * **External**: If sending through a standard `@gmail.com` account or public users will interact with Google Sign-In.
3. Click **Create**.
4. Fill in the App Information:
   * **App Name**: `ImageShrink Pro`
   * **User support email**: `support@yourdomain.com` (or your verified Gmail address)
   * **Developer contact information**: `admin@yourdomain.com`
5. **Scopes**:
   * Click **Add or Remove Scopes**.
   * Add the transactional email sending scope:
     * `https://www.googleapis.com/auth/gmail.send` *(Minimum required privilege)*
   * For Google Sign-In, add:
     * `openid`
     * `https://www.googleapis.com/auth/userinfo.email`
     * `https://www.googleapis.com/auth/userinfo.profile`
6. If the app is in "Testing" mode, add your sending Gmail address as a **Test User**.

---

## 3. Create OAuth 2.0 Credentials

### 3.1 Credentials for Gmail Transactional Email Sending
1. Go to **APIs & Services** > **Credentials**.
2. Click **Create Credentials** > **OAuth client ID**.
3. Application Type: **Web application**.
4. Name: `ImageShrink Pro Gmail Dispatcher`.
5. **Authorized redirect URIs**:
   * Add `https://developers.google.com/oauthplayground` *(Used to securely generate your long-lived refresh token)*.
   * Add your production callback: `https://yourdomain.com/api/v2/auth/google/callback`.
6. Click **Create**.
7. Note down your **Client ID** and **Client Secret**.

### 3.2 Generate Long-Lived Refresh Token via OAuth 2.0 Playground
1. Visit the [Google OAuth 2.0 Playground](https://developers.google.com/oauthplayground).
2. Click the gear icon (**OAuth 2.0 configuration**) in the top right:
   * Check **Use your own OAuth credentials**.
   * Enter your `OAuth Client ID` and `OAuth Client Secret`.
3. In Step 1 (Select & authorize APIs):
   * In the input box, enter: `https://www.googleapis.com/auth/gmail.send`
   * Click **Authorize APIs**.
   * Sign in using your verified sender Gmail or Google Workspace account.
   * Grant permission to send email on your behalf.
4. In Step 2 (Exchange authorization code for tokens):
   * Click **Exchange authorization code for tokens**.
5. Copy the generated **Refresh token**.

---

## 4. Environment Variables Configuration

Set these variables in your `.env` file on your server or container:

```bash
# ==============================================================================
# Google Gmail API Transactional Email Configuration
# ==============================================================================
APP_BASE_URL=https://yourdomain.com
GMAIL_CLIENT_ID=your-client-id.apps.googleusercontent.com
GMAIL_CLIENT_SECRET=your-client-secret
GMAIL_REFRESH_TOKEN=your-authorized-refresh-token
GMAIL_SENDER_EMAIL=notifications@yourdomain.com
GMAIL_SENDER_NAME=ImageShrink Pro Security

# 32-byte Fernet key for encrypting refresh tokens at rest in database
# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
GMAIL_TOKEN_ENCRYPTION_KEY=your-32-byte-base64-encryption-key

# Daily sending quota limit (500 for standard Gmail, 2000 for Google Workspace)
GMAIL_DAILY_QUOTA_LIMIT=500

# Optional Google Sign-In (OpenID Connect)
GOOGLE_AUTH_CLIENT_ID=your-signin-client-id.apps.googleusercontent.com
GOOGLE_AUTH_CLIENT_SECRET=your-signin-client-secret
GOOGLE_AUTH_REDIRECT_URI=https://yourdomain.com/api/v2/auth/google/callback
```

---

## 5. SPF, DKIM, and DMARC Setup (Google Workspace)

To guarantee high deliverability and prevent authentication emails from being flagged as spam, configure these DNS records on your domain registrar (e.g. Cloudflare, Route53, GoDaddy):

### 5.1 SPF Record (TXT)
Add or update the TXT record for your apex domain (`@`):
* **Host**: `@`
* **Type**: `TXT`
* **Value**: `v=spf1 include:_spf.google.com ~all`

### 5.2 DKIM Record (TXT)
1. Go to [Google Workspace Admin Console](https://admin.google.com) > **Apps** > **Google Workspace** > **Gmail** > **Authenticate email**.
2. Select your domain and click **Generate new record**.
3. Choose 2048-bit key length and selector (default: `google`).
4. Add the TXT record to your DNS:
   * **Host**: `google._domainkey`
   * **Type**: `TXT`
   * **Value**: *(Paste the public key string generated by Google Admin)*
5. Wait 15 minutes, return to Google Admin Console, and click **Start authentication**.

### 5.3 DMARC Policy (TXT)
Add the DMARC TXT record:
* **Host**: `_dmarc`
* **Type**: `TXT`
* **Value**: `v=DMARC1; p=quarantine; rua=mailto:dmarc-reports@yourdomain.com; pct=100; sp=quarantine`

---

## 6. Daily Sending Quotas and Limits

Google enforces the following daily limits on API transactional sending:

| Account Type | Daily Sending Limit | Burst / Minute Limit |
|---|---|---|
| Standard Personal Gmail (`@gmail.com`) | 500 emails / rolling 24h | ~100 emails / minute |
| Google Workspace Trial Account | 500 emails / rolling 24h | ~100 emails / minute |
| Google Workspace Paid Account | 2,000 emails / rolling 24h | ~1,000 emails / minute |

**Protection in ImageShrink Pro**:
* The system monitors 24-hour delivery volume in `email_delivery_logs`.
* When `GMAIL_DAILY_QUOTA_LIMIT` is reached, transient submissions fail gracefully without crashing.
* Idempotency keys prevent duplicate email dispatches if an external webhook or button is retried.

---

## 7. Security Architecture

1. **At-Rest Token Encryption**: All refresh tokens stored in database or memory are encrypted using AES-128-CBC + HMAC-SHA256 (Fernet) derived from `GMAIL_TOKEN_ENCRYPTION_KEY`.
2. **Access Token Lifecycle**: Access tokens expire after 3,600 seconds. The service automatically detects expiration and refreshes the token in the background using Google's OAuth endpoint.
3. **Audit Trail**: Every email dispatch attempt (recipient, template name, message ID, timestamp, retry count) is logged in `email_delivery_logs`.
4. **Least Privilege**: The scope used (`https://www.googleapis.com/auth/gmail.send`) only allows sending messages. It cannot read or delete existing user emails.

