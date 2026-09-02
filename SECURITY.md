# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| `0.1.x` | :white_check_mark: |
| < 0.1   | :x:                |

---

## Local Privacy Guarantee

This project is built with an **offline-first and privacy-by-design** architecture:
- All ASR, Machine Translation, and Voice Cloning TTS inference runs 100% locally on your machine's hardware.
- No audio frames, transcriptions, or meeting logs are ever uploaded to cloud endpoints or third-party servers.
- The web dashboard binds exclusively to `127.0.0.1` by default.

---

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please **do not open a public issue**. Instead, follow these steps:

1. Send an email or private message via the repository owner's GitHub profile.
2. Include details of the vulnerability:
   - Type of issue (e.g., local server privilege escalation, path traversal, untrusted input injection).
   - Step-by-step instructions to reproduce the issue.
   - Affected components and version.
3. You will receive an acknowledgment within 48 hours.
4. We will coordinate a fix and release a security advisory once patched.

Thank you for helping keep this project secure and private for everyone!
