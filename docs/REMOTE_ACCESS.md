# ERIS — Secure Remote Access & Cross-Device Guide

This guide explains how to access your ERIS AI assistant from your phone, laptop, or remote devices outside your home Wi-Fi network safely and securely.

---

## 1. Security Architecture (ERIS Charter §3 & §27)

Exposing a personal AI assistant directly to the public internet using traditional router port forwarding introduces severe security vulnerabilities.

ERIS enforces a **Zero-Trust Remote Access Model**:
1. **API Key Authentication**: Enables `ERIS_AUTH_ENABLED=true` in your `.env` file to require an authentication token (`ERIS_API_KEY`) for all engine requests.
2. **Encrypted Tunneling**: Uses an encrypted private overlay network (Tailscale) or zero-trust cloud tunnel (Cloudflare Tunnel) rather than opening public inbound ports.

---

## 2. Setting Up API Key Security

Before accessing ERIS remotely, configure authentication in your `.env` file:

```env
# Enable API Key authentication
ERIS_AUTH_ENABLED=true

# Set your secure private key
ERIS_API_KEY=your_super_secret_private_key_here
```

Restart the ERIS server:
```powershell
python -m apps.api.main
```
When you open the Web UI, ERIS will prompt you to enter `ERIS_API_KEY` once, saving it securely in your browser's local storage.

---

## 3. Option A: Tailscale (Recommended for Personal Devices)

Tailscale creates a secure, encrypted peer-to-peer mesh network between your devices without exposing any public ports.

### Steps:
1. **Install Tailscale** on your main PC running ERIS: [tailscale.com](https://tailscale.com).
2. **Install Tailscale** on your mobile phone, tablet, or secondary laptop.
3. Sign in to Tailscale on both devices.
4. Note your host PC's **Tailscale IPv4 Address** (e.g. `100.115.92.40`) or MagicDNS hostname (e.g. `eris-pc.tailnet.ts.net`).
5. Open your browser on your phone while connected to Tailscale and visit:
   `http://100.115.92.40:8000/` or `http://eris-pc.tailnet.ts.net:8000/`
6. Authenticate with your `ERIS_API_KEY` when prompted.

---

## 4. Option B: Cloudflare Tunnel (For Web Address Access)

Cloudflare Tunnel creates an encrypted outbound tunnel connecting your local FastAPI server to Cloudflare's edge network.

### Steps:
1. Download `cloudflared` on your PC: [developers.cloudflare.com/cloudflare-one/connections/connect-networks](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks).
2. Run a quick tunnel:
   ```powershell
   cloudflared tunnel --url http://localhost:8000
   ```
3. Copy the generated `trycloudflare.com` HTTPS URL (e.g., `https://random-words.trycloudflare.com`).
4. Visit the HTTPS URL from any device. Ensure `ERIS_AUTH_ENABLED=true` is set so only authorized requests are accepted.

---

## 5. Security Checklist

- [x] Never leave `ERIS_AUTH_ENABLED=false` when accessing over public networks or Cloudflare Tunnels.
- [x] Do not hardcode secrets or commit `.env` files to git repositories.
- [x] Rotate `ERIS_API_KEY` if exposed.
