# AirDrop — Offline File Transfer System

AirDrop is an independent, local, peer-to-peer wireless file transfer system inspired by Apple AirDrop. It allows direct, high-speed file transfers between a Windows laptop and mobile smartphones (Android and iOS) using local Wi-Fi without requiring an active internet connection, Bluetooth, third-party cloud relays, or native mobile application installations.

---

## 1. Project Overview & Problem Statement

### The Problem
Traditional file transfer options across heterogeneous operating systems (Windows, Android, iOS) suffer from significant drawbacks:
- **Cloud storage services** (Google Drive, Dropbox, iCloud) require uploading files to remote servers across the public internet, consuming cellular bandwidth, introducing latency, and compromising privacy.
- **Bluetooth transfers** have severe bandwidth constraints (rarely exceeding 200–300 KB/s), making large media files, videos, and archives impractical.
- **Proprietary ecosystems** (such as Apple AirDrop or Quick Share) are intentionally walled off or unreliable when bridging Windows laptops and cross-platform mobile phones.
- **Third-party ad-heavy mobile applications** require installing untrusted apps on the recipient's phone, which often demand intrusive permissions (contacts, storage, location).

### The AirDrop Solution
AirDrop bridges Windows laptops and mobile devices through an **offline, browser-based peer-to-peer transport protocol**. 
- The laptop acts as the local HTTP and WebSocket host, bound to `0.0.0.0` over the local Wi-Fi interface or a private Windows Mobile Hotspot.
- The phone accesses the system through its default mobile browser (Chrome on Android, Safari on iOS) simply by scanning a dynamic QR code.
- Files stream directly over local Wi-Fi radio frequencies at standard LAN speeds (typically 10 MB/s to 40+ MB/s depending on the 802.11 Wi-Fi generation).
- Cryptographic SHA-256 hashing guarantees end-to-end data integrity.

---

## 2. Wireless Communication Concept & Network Architecture

### Transport Layer & Medium
- **Physical/Data Link Medium:** Wi-Fi (IEEE 802.11 b/g/n/ac/ax) radio waves.
- **Network Layer:** IPv4 within private local subnets (`192.168.x.x`, `10.x.x.x`, `172.16-31.x.x`).
- **Transport Layer:** TCP / IP.
- **Application Layer:** HTTP/1.1 REST endpoints and bidirectional WebSockets (`ws://`).

> **College Presentation Note:**  
> Wi-Fi is the *physical data transport medium*, while the local wireless access point or Windows Mobile Hotspot provides the *layer-2/layer-3 link layer* between the devices. The internet (WAN) is never contacted; all IP packets travel directly from the laptop's Wi-Fi network interface card (NIC) across the router or hotspot radio to the phone's Wi-Fi antenna.

```
+------------------------------------------------------------------+
|                     OFFLINE LOCAL WI-FI SUBNET                    |
|             (e.g., Windows Mobile Hotspot / Local Router)        |
+------------------------------------------------------------------+
                ^                                    ^
                |                                    |
     Local HTTP / WebSocket               Local HTTP / WebSocket
   Streaming over TCP/IP                Streaming over TCP/IP
                |                                    |
                v                                    v
+-------------------------------+    +-------------------------------+
|      HOST: Windows Laptop     |    |     CLIENT: Mobile Phone      |
|  - FastAPI Local Server       |    |  - Mobile Web Browser         |
|  - IP Binding: 0.0.0.0:8000   |    |    (Chrome, Safari, Firefox)  |
|  - Dynamic QR Generator       |    |  - QR Code Scanner / Camera   |
|  - SHA-256 Stream Hasher      |    |  - Touch-Friendly File Picker |
|  - SQLite Transfer History    |    |  - Native Browser Download    |
|  - Isolated transfers/ Folder |    |  - Live Progress & Speed Calc |
+-------------------------------+    +-------------------------------+
```

---

## 3. Core Features

1. **True Offline Operation:** Operates with 100% functionality on a Wi-Fi router with no internet cable plugged in, or via a Windows Mobile Hotspot with cellular data disabled.
2. **Zero Native Mobile App Install:** Recipients interact purely through modern mobile browsers using standard HTML5, CSS3, Fetch API, and WebSockets.
3. **Dynamic QR Code Pairing:** Automatically discovers the laptop's LAN IP address, generates an in-memory SVG/PNG QR code containing the URL, and displays it on the laptop screen.
4. **Cryptographic 6-Digit Pairing & Approval:** Unauthorized devices are prevented from accessing or uploading files. Mobile users enter a short-lived 6-digit code shown on the laptop, and the laptop operator must explicitly click **Approve Device**.
5. **Bidirectional Transfer:**
   - **Laptop to Phone:** Laptop stages files; phone views them in an incoming files feed and downloads with standard browser download mechanics.
   - **Phone to Laptop:** Mobile touch-friendly picker uploads photos, videos, documents, or ZIP archives directly to the laptop's storage.
6. **Streaming & Large File Support:** Chunks streamed in 64 KB buffers to isolated `.tmp` files. Zero memory ballooning, with a configurable 2 GB file size limit.
7. **Accurate Speed & Progress Dashboard:** Real-time transfer metrics calculation: percentage, bytes transferred, elapsed time, current transfer speed (KB/s or MB/s), and estimated time remaining (ETA).
8. **End-to-End SHA-256 Integrity Verification:** Computes sender and receiver hashes; strictly differentiates between self-calculated hashes and sender-verified matches.
9. **Transfer History & SQLite Audit Log:** Records transfer direction, filename, size, duration, average speed, timestamp, and verification status. Includes a single-click "Clear History" action.
10. **Clean, Credible Minimalist Aesthetic:** Apple-inspired clean typography, dark/light theme toggle, vector SVG icons, and privacy/terms pages without AI gimmicks.

---

## 4. Hardware & Software Requirements

### Laptop (Host)
- **Operating System:** Windows 10 or Windows 11 (64-bit).
- **Wi-Fi Hardware:** 802.11n, 802.11ac, or 802.11ax Wi-Fi adapter.
- **Python:** Python 3.11, 3.12, or newer.
- **Ports:** Port `8000` (configurable via `.env` or environment variables).

### Mobile Phone (Client)
- **Operating System:** Android 8.0+ or iOS 13+.
- **Browser:** Any modern browser supporting WebSockets and Fetch API (Chrome, Safari, Firefox, Edge, Brave, Samsung Internet).
- **Wi-Fi:** Wi-Fi connection capability.

---

## 5. Quick Start Instructions (Windows)

### Option A: Automatic 1-Click Launch (`run.bat`)
1. Double-click the included `run.bat` script in the root directory.
2. The script will:
   - Verify Python installation.
   - Create an isolated virtual environment (`.venv`).
   - Install dependencies from `requirements.txt`.
   - Detect your usable local LAN IP.
   - Start the server on `0.0.0.0:8000`.
   - Print the local access URL.

### Option B: Manual Command Line
```powershell
# 1. Navigate to the project directory
cd airlink

# 2. Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\activate

# 3. Install pinned dependencies
pip install -r requirements.txt

# 4. Run the FastAPI application
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## 6. Transfer Procedures

### Step 1: Connect Devices to the Same Local Network
- **Option 1 (Home/Office Wi-Fi):** Connect both laptop and phone to the same Wi-Fi router.
- **Option 2 (Windows Mobile Hotspot — Zero Internet Needed):**
  1. On your Windows laptop, go to **Settings &rarr; Network & internet &rarr; Mobile hotspot**.
  2. Toggle **Mobile hotspot** to **On**.
  3. Note the Network name (SSID) and password.
  4. On your mobile phone, connect to this Wi-Fi hotspot.
  5. *Even if Windows displays "No Internet", AirLink works completely.*

### Step 2: Open AirLink
- On your laptop, open your web browser to:
  ```
  http://localhost:8000
  ```
- The dashboard will show your laptop's Wi-Fi IP address (e.g., `http://192.168.137.1:8000` or `http://192.168.29.249:8000`) and the QR code.

### Step 3: Scan QR Code & Pair
1. On your phone, open your Camera or browser and scan the QR code (or type the URL into mobile Chrome/Safari).
2. The phone screen will prompt for the **6-Digit Pairing Code** displayed on the laptop.
3. Type the 6 digits on the phone and tap **Authorize Device**.
4. The laptop will immediately display a banner:  
   `Device Authorization Request: Chrome on Android (192.168.29.105) [Reject] [Approve Device]`
5. Click **Approve Device** on the laptop. The phone is now authorized.

### Step 4: Transfer Files
- **To Send from Phone to Laptop:**
  - On the phone, tap the **Upload Files to Laptop** card.
  - Choose one or more photos, videos, or documents.
  - The live progress bar shows bytes transferred, transfer speed (e.g., `18.4 MB/s`), and calculated SHA-256 hash.
  - Files are saved immediately into the laptop's `transfers/` directory.
- **To Send from Laptop to Phone:**
  - On the laptop, drag and drop files onto the **Stage Files for Mobile Phone** card (or click to browse).
  - Click **Transfer Now**.
  - The phone interface automatically refreshes via WebSocket, showing the files in the **Available Files to Download** list.
  - Tap **Download** on the phone to save the file.

---

## 7. Security Architecture & Limitations

### Built-in Protections
1. **Server-Side Token Authentication:** Remote clients cannot access `/api/files`, `/api/uploads`, or `/api/transfers` without an approved session token.
2. **Short-Lived Dynamic Pairing Codes:** Pairing codes expire every 5 minutes and are regenerated with cryptographic randomness (`secrets.randbelow`).
3. **Path Traversal Shielding:** All incoming filenames are sanitized through `sanitize_filename()`. Null bytes, directory separators (`/`, `\`), `..`, and Windows reserved names (`CON`, `PRN`, `AUX`, `NUL`) are neutralized.
4. **Temporary File Isolation:** Uploads are streamed into temporary `.tmp` files. If an upload is aborted, interrupted, or exceeds the 2 GB size limit, the partial `.tmp` file is immediately unlinked.
5. **No Filesystem Traversal:** Remote clients can only access files explicitly staged in the active session. Arbitrary disk browsing is strictly prohibited.

### Security Limitations (Documented for Academic Transparency)
- The initial version uses standard unencrypted HTTP (`http://`) over a local private subnet. Because transfers occur over a trusted WPA2/WPA3 private home Wi-Fi or laptop hotspot, traffic is protected by Wi-Fi link-layer encryption.
- It is not end-to-end encrypted at the application layer (TLS). Do not operate AirLink on untrusted public open Wi-Fi networks (e.g., airports, coffee shops) without establishing a direct private hotspot.

---

## 8. REST & WebSocket API Reference

| Method | Endpoint | Access | Description |
|---|---|---|---|
| `GET` | `/` | Public | Serves the responsive web application dashboard. |
| `GET` | `/privacy` | Public | Serves the local Privacy Policy page. |
| `GET` | `/terms` | Public | Serves the local Terms of Service page. |
| `GET` | `/api/health` | Public | Server status, uptime, and local IP. |
| `GET` | `/api/network/info` | Public | Discovered local IPs, access URL, and QR code SVG/PNG. |
| `GET` | `/api/session/state` | Public / Token | Current role (host, client, guest), pairing code, and pending requests. |
| `POST` | `/api/pair/request` | Public | Submits a 6-digit pairing code from phone. |
| `GET` | `/api/pair/status/{id}` | Public | Polls status of a pairing request. |
| `POST` | `/api/pair/approve` | Host Only | Approves client pairing and issues session token. |
| `POST` | `/api/pair/reject` | Host Only | Rejects client pairing request. |
| `POST` | `/api/pair/new-code` | Host Only | Regenerates a fresh 6-digit pairing code. |
| `POST` | `/api/session/disconnect` | Authenticated | Revokes current session token. |
| `POST` | `/api/stage-files` | Host Only | Stages files on laptop for phone download. |
| `GET` | `/api/files` | Authenticated | Lists currently staged files available for download. |
| `GET` | `/api/files/{id}/download` | Authenticated | Streams file download with SHA-256 header. |
| `DELETE` | `/api/files/{id}` | Host Only | Removes a file from staged list. |
| `POST` | `/api/uploads` | Authenticated | Streaming file upload with on-the-fly SHA-256 computation. |
| `GET` | `/api/transfers` | Authenticated | Retrieves transfer history list from SQLite. |
| `DELETE` | `/api/transfers` | Host Only | Clears transfer history records. |
| `GET` | `/api/transfers/{id}/download` | Authenticated | Downloads a received file from local transfers storage. |
| `WS` | `/ws` | Authenticated | WebSocket endpoint for real-time live transfer progress and events. |

---

## 9. Automated Testing

AirLink includes a comprehensive test suite covering all security, transfer, checksum, and routing specifications.

To run the automated tests:
```powershell
.\.venv\Scripts\pytest.exe -v
```

### Verified Test Cases:
1. `test_health_endpoint`: Server diagnostics and uptime reporting.
2. `test_network_info_endpoint`: LAN IP detection and QR code generation.
3. `test_page_routes`: HTML template rendering (`/`, `/terms`, `/privacy`).
4. `test_unauthorized_access_rejection`: Rejection of unauthenticated clients on protected endpoints (HTTP 401).
5. `test_pairing_workflow_and_approval`: 6-digit PIN validation, pending state, host approval, token issuance, and session disconnect.
6. `test_pairing_code_expiration`: Automatic expiration of stale pairing codes.
7. `test_filename_sanitization_and_path_traversal`: Protection against `../../`, null bytes, illegal characters, and Windows device names.
8. `test_file_upload_and_sha256_verification`: Streaming chunked upload with matching SHA-256 checksum verification.
9. `test_upload_with_mismatched_checksum`: Detection and flagging of corrupted or mismatched sender hashes.
10. `test_staging_and_downloading_file`: Staging, download streaming, and `X-Checksum-SHA256` verification.
11. `test_oversized_file_rejection`: Immediate HTTP 413 rejection and `.tmp` cleanup when file exceeds size limit.
12. `test_transfer_history_recording_and_clearing`: SQLite persistence of transfer records and history reset.
13. `test_cleanup_incomplete_uploads`: Automated purging of orphaned temporary files.

---

## 10. Troubleshooting Guide

### Issue: Phone browser displays "Cannot Connect" or "Site Can't Be Reached"
- **Cause 1: Windows Firewall:** When AirLink started, Windows Firewall may have blocked incoming traffic on port 8000.  
  *Fix:* In Windows Defender Firewall, allow Python (`python.exe`) on **Private Networks**.
- **Cause 2: Public Network Profile:** If your Wi-Fi is marked as "Public", Windows blocks incoming LAN requests.  
  *Fix:* Go to Windows Settings &rarr; Network & internet &rarr; Wi-Fi &rarr; Click your network &rarr; Select **Private network**.
- **Cause 3: AP Isolation:** Some university or public Wi-Fi networks block device-to-device communication ("Client Isolation").  
  *Fix:* Use the **Windows Mobile Hotspot** method described in Section 6.

### Issue: The IP address shown is `127.0.0.1`
- **Cause:** The laptop is not connected to any Wi-Fi network or hotspot.
- **Fix:** Connect the laptop to Wi-Fi or turn on Windows Mobile Hotspot, then refresh AirLink.

---

## 11. Future Enhancements

The modular design of AirLink permits several natural extensions for future academic or production work:
1. **Native Wi-Fi Direct (P2P):** Integrating native Windows Wi-Fi Direct APIs (`Windows.Devices.WiFiDirect`) for automatic zero-configuration device discovery without requiring a router.
2. **mDNS / Bonjour Service Discovery:** Broadcasting an `_airlink._tcp.local` zero-conf service so client browsers can navigate to `http://airlink.local:8000`.
3. **Application-Layer TLS / Self-Signed HTTPS:** Generating ephemeral in-memory TLS certificates to enable WebRTC data channels for browser-to-browser UDP transfers.
4. **Resumable Chunked Uploads:** Implementing the open `tus.io` resumable upload protocol to pause and resume interrupted multi-gigabyte transfers.
5. **Native Companion Clients:** Lightweight native clients written in Kotlin (Android) and C# / WinUI 3 (Windows) for background file drop and system tray integration.
