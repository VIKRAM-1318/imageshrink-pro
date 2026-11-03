# ImageShrink Pro — Privacy Policy

**Effective Date:** November 3, 2026  
**Last Updated:** November 3, 2026  
**Version:** 2.0.0

ImageShrink Pro ("we," "us," "our," or "ImageShrink Pro") operates the bulk image optimization and format conversion SaaS platform accessible via web interfaces and internal services. We are dedicated to protecting your personal data, respecting your digital privacy, and maintaining complete transparency regarding how digital assets are processed, stored, and deleted across our infrastructure.

This Privacy Policy explains in detail our practices regarding the collection, handling, processing, retention, protection, and disclosure of personal data and digital media assets when you access or use ImageShrink Pro.

---

## 1. Core Privacy Commitments & Principles

We operate under five non-negotiable architectural privacy principles:

1. **Zero AI/ML Training on Customer Data:** Your images, files, metadata, and visual contents are strictly used for image compression and conversion requests. We will **never** use your images to train, fine-tune, benchmark, or evaluate machine learning models, neural networks, or generative AI algorithms.
2. **Strict Ephemeral Lifecycle (24-Hour Auto-Purge):** All uploaded original files, processed output files, and compiled ZIP archives are stored temporarily in isolated workspace directories and permanently, irreversibly purged within twenty-four (24) hours (`JOB_TTL_SECONDS = 86400`).
3. **No Unnecessary Data Harvesting:** We do not collect names, phone numbers, contacts, or invasive tracking beacons unless you voluntarily create an account or subscribe to a paid tier.
4. **Data Ownership Retained by You:** You retain 100% exclusive intellectual property rights and copyright in all images submitted to ImageShrink Pro.
5. **No Sale of Personal Data:** We never sell, lease, rent, trade, or monetize your personal data or uploaded media to data brokers, advertising networks, or third parties.

---

## 2. Information We Collect

### A. Digital Media Uploads (Image Data)
* **Uploaded Files:** Files you upload for optimization, including JPEG, PNG, WebP, AVIF, GIF, TIFF, BMP, HEIC/HEIF, SVG, and ICO files (up to 35 MB per file and batches up to 500 images for registered Pro users).
* **Embedded Metadata (EXIF/ICC):** Depending on your chosen optimization mode:
  * In *Lossless Mode*: All EXIF metadata, ICC color profiles, and orientation tags are preserved verbatim to maintain professional photography standards.
  * In *Visual Lossless & Custom Modes*: Non-essential metadata (camera serial numbers, GPS geolocation coordinates, thumbnail previews) is stripped by default to maximize byte savings and eliminate accidental location disclosure, while preserving necessary orientation and standard color tags.
* **Pixel and Format Attributes:** Image dimensions, color space, channel depth, and structural metrics (SSIM and PSNR) computed in-memory to verify perceptual visual quality.

### B. User Account Data (Optional Registered Users)
* **Account Information:** When you register for an account, we collect your full name, email address, and a cryptographically salted and hashed representation of your password (generated via PBKDF2-HMAC-SHA256 with dynamic salt and 600,000 iterations). We never store plaintext passwords.
* **Subscription Status:** Plan tier (`Free`, `Pro`, `Business`), subscription expiration timestamp, remaining quota units, and billing customer identifiers.

### C. Technical, Operational, and Diagnostic Data
* **Server Logs:** When you interact with our service, our web application firewall and security middleware log standard request metadata: client IP address, User-Agent header, HTTP request method and path, response status code, and request timestamp.
* **Security & Audit Logs:** To prevent brute-force attacks and unauthorized access to administrative portals, we record failed login attempts, IP address rate-limiting counters, and session invalidation events. These audit records contain no image data, credentials, or session tokens.
* **Billing Information:** Payment transactions are handled directly through certified Level 1 PCI-DSS compliant payment gateways (Stripe and Razorpay). We do not collect, process, or store credit card numbers, CVV codes, or full banking details on our servers.

---

## 3. How We Process and Use Your Information

We process collected data exclusively for the following legitimate business and service purposes:

1. **Delivering the Image Optimization Service:**
   * Decoding binary image data to detect genuine MIME types using magic bytes (e.g., preventing disguised executable payloads).
   * Executing format-specific optimization routines (MozJPEG quantization, Oxipng/Zopfli deflate filtering, WebP/AVIF encoding, SVG safe sanitization).
   * Bundling processed media into streaming ZIP archives for batch download.
2. **Account Management & Authentication:**
   * Verifying user credentials and issuing JSON Web Tokens (JWT) or secure HTTP-only session cookies.
   * Enforcing plan-specific quota limits (e.g., 50 files for Free tier vs. 500 files for Pro tier).
3. **Security, Abuse Prevention, and Integrity:**
   * Detecting and rejecting malicious decompression bombs (pixel bombs designed to trigger denial-of-service).
   * Protecting against credential stuffing, brute-force attacks, and CSRF attempts.
4. **Legal Compliance:**
   * Fulfilling statutory tax and accounting requirements for paid commercial invoices.
   * Complying with binding court orders or statutory law enforcement obligations.

---

## 4. Digital Asset Lifecycle & Automated Deletion

We enforce a strict temporal lifecycle on all user files:

| Stage | Duration | Processing State |
| :--- | :--- | :--- |
| **Ingestion** | Instantaneous | Received via encrypted TLS 1.3 streams into isolated temporary buffers. |
| **Processing** | Typically < 1–5 seconds | Converted/optimized in volatile memory and partitioned filesystem storage. |
| **Download Window** | Up to 24 Hours | Accessible via unguessable, cryptographically random UUID v4 download URLs. |
| **Permanent Purge** | Automatic after 24 Hours | Filesystem unlinking and storage cleanup permanently destroys all files. |

> **Automated Purge Guarantee:** Our storage manager runs continuous automated cleanup sweeps (`storage.cleanup_old_files(max_age_seconds=86400)`). Once deleted, image files cannot be retrieved, reconstructed, or recovered by any party, including ImageShrink Pro engineering staff.

---

## 5. Explicit Machine Learning & AI Disclaimer

**We provide an unconditional, irrevocable guarantee regarding Artificial Intelligence (AI) and Machine Learning (ML):**
* We **do not** use customer-uploaded images, graphics, photographs, or vectors to train, test, or validate neural networks, computer vision models, or generative AI models (such as Stable Diffusion, Midjourney, DALL-E, or proprietary classifiers).
* We **do not** sell, license, or provide access to your images to third-party AI companies, research labs, or web crawlers.
* All processing engines deployed within ImageShrink Pro rely on algorithmic, deterministic mathematical compression algorithms (discrete cosine transform, Huffman/arithmetic coding, palette quantization, and entropy coding).

---

## 6. Cookies and Tracking Technologies

* **Essential Authentication Cookies:** We use secure, HTTP-only, SameSite-restricted cookies strictly for administrative authentication and CSRF protection (`isp_admin_session`, `isp_csrf_token`). These cookies are strictly necessary for application security and do not track your activity across third-party websites.
* **Local Storage:** Client-side tokens (`isp_token`) and user interface theme preferences (`dark` / `light`) are saved in your browser's `localStorage` for session persistence.
* **No Third-Party Advertising Trackers:** ImageShrink Pro contains zero Google AdSense, zero Facebook Pixels, and zero intrusive commercial marketing beacons.

---

## 7. Data Sharing and Third-Party Sub-Processors

We do not sell, trade, or share your personal data with third parties except with trusted infrastructure sub-processors essential to providing the SaaS service:

| Sub-Processor | Role / Activity | Data Transferred | Compliance Standard |
| :--- | :--- | :--- | :--- |
| **Stripe, Inc.** | Payment processing | Billing contact info, card details (direct) | PCI-DSS Level 1 |
| **Razorpay Software** | Payment processing | Billing contact info, UPI/card data | PCI-DSS Level 1 |
| **AWS / Cloudflare** | Cloud hosting, CDN, and DDoS mitigation | Encrypted IP traffic in transit | SOC 2 Type II, ISO 27001 |

All sub-processors are vetted for stringent security controls and are bound by Data Processing Addendums (DPAs) requiring equivalent privacy protection.

---

## 8. Data Security Architecture

We apply comprehensive technical and organizational safeguards:
* **Transport Encryption:** All traffic is encrypted in transit using Transport Layer Security (TLS 1.3/1.2) with modern cipher suites.
* **Storage Isolation:** Uploads are quarantined into tenant-isolated directory paths mapped to random UUIDs. No public directory listing or file browsing is enabled.
* **Defensive HTTP Headers:** All responses include `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection: 1; mode=block`, and strict `Permissions-Policy`.
* **Private Administration:** Administrative routes and databases are completely isolated behind brute-force protection, IP lockouts, and cryptographic password hashing. Public API documentation interfaces are disabled in production.

---

## 9. Your Rights Under GDPR & CCPA/CPRA

Depending on your geographical jurisdiction (including the European Economic Area, United Kingdom, and State of California), you hold distinct legal rights:

### European Union & UK Residents (GDPR / UK GDPR)
* **Right of Access (Art. 15):** Request confirmation of whether we process personal data relating to you and obtain a copy.
* **Right to Rectification (Art. 16):** Request correction of inaccurate personal profile data.
* **Right to Erasure / "Right to be Forgotten" (Art. 17):** Request the deletion of your account and personal profile data. (Note: Uploaded images are automatically deleted within 24 hours).
* **Right to Restriction of Processing (Art. 18) & Data Portability (Art. 20):** Obtain your registered account data in a structured, commonly used, machine-readable format.
* **Right to Lodge a Complaint:** You have the right to lodge a complaint with your local Data Protection Authority (DPA).

### California Residents (CCPA / CPRA)
* **Right to Know and Access:** Request details regarding categories of personal information collected.
* **Right to Delete:** Request deletion of personal information collected from you.
* **Right to Opt-Out of Sale or Sharing:** We do not sell or share personal information for cross-context behavioral advertising.
* **Right to Non-Discrimination:** We will not discriminate against you in pricing, service quality, or availability for exercising your CCPA rights.

---

## 10. Children's Privacy

ImageShrink Pro is designed and intended solely for commercial, professional, and general consumer audiences aged 16 and older. We do not knowingly solicit or collect personal information from children under 13 (or under 16 in certain jurisdictions) in adherence to the Children's Online Privacy Protection Act (COPPA). If we discover that personal data from a child has been collected without parental consent, we will immediately take steps to permanently delete that information.

---

## 11. Changes to This Privacy Policy

We may periodically revise this Privacy Policy to reflect operational improvements, technological changes, or evolving regulatory obligations. Material modifications will be announced via in-app banners or via email notification to registered account holders prior to the effective date. Continued use of ImageShrink Pro following published changes constitutes acknowledgment of the updated terms.

---

## 12. Contact Information & Data Protection Officer

For privacy inquiries, GDPR/CCPA data subject access requests, or security disclosures, contact our privacy engineering team:

* **Legal Entity:** ImageShrink Pro Privacy Operations  
* **Data Protection Officer (DPO):** `privacy@imageshrinkpro.com`  
* **Security & Vulnerability Disclosure:** `security@imageshrinkpro.com`  
* **Physical Address:** ImageShrink Pro Global Infrastructure, 100 Tech Enterprise Blvd, Suite 400, San Francisco, CA 94107, USA  

