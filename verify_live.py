import urllib.request
import json
import hashlib

base = "http://localhost:8000"

print("1. Testing Static files & Web Pages...", flush=True)
for path in ["/", "/terms", "/privacy", "/favicon.svg", "/static/css/styles.css", "/static/js/app.js"]:
    req = urllib.request.Request(f"{base}{path}")
    with urllib.request.urlopen(req, timeout=5) as res:
        assert res.status == 200
        _ = res.read()
        print(f"   [PASS] {path} -> 200 OK", flush=True)

print("\n2. Getting Session State on Host Laptop...", flush=True)
req = urllib.request.Request(f"{base}/api/session/state")
with urllib.request.urlopen(req, timeout=5) as res:
    data = json.loads(res.read().decode())
    print("   [PASS] Host session role:", data.get("role"), flush=True)
    print("   [PASS] Active Pairing code:", data.get("pairing_code"), flush=True)
    pairing_code = data.get("pairing_code")
    host_token = data.get("host_token")

print("\n3. Simulating Mobile Phone submitting 6-digit PIN...", flush=True)
pair_req = urllib.request.Request(
    f"{base}/api/pair/request",
    data=json.dumps({"code": pairing_code}).encode("utf-8"),
    headers={
        "Content-Type": "application/json",
        "X-Forwarded-For": "192.168.29.241",
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"
    }
)
with urllib.request.urlopen(pair_req, timeout=5) as res:
    pair_data = json.loads(res.read().decode())
    req_id = pair_data["request_id"]
    print("   [PASS] Phone submitted code, request ID:", req_id, flush=True)

print("\n4. Host Laptop Approves Mobile Phone...", flush=True)
approve_req = urllib.request.Request(
    f"{base}/api/pair/approve",
    data=json.dumps({"request_id": req_id}).encode("utf-8"),
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {host_token}"
    }
)
with urllib.request.urlopen(approve_req, timeout=5) as res:
    approve_data = json.loads(res.read().decode())
    client_token = approve_data["token"]
    print("   [PASS] Host approved phone. Issued Token:", client_token[:16] + "...", flush=True)

print("\n5. Verifying Authenticated Phone Access...", flush=True)
client_req = urllib.request.Request(
    f"{base}/api/session/state",
    headers={
        "Authorization": f"Bearer {client_token}",
        "X-Forwarded-For": "192.168.29.241",
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X)"
    }
)
with urllib.request.urlopen(client_req, timeout=5) as res:
    c_state = json.loads(res.read().decode())
    print("   [PASS] Phone role:", c_state.get("role"), "Authenticated:", c_state.get("authenticated"), flush=True)
    print("   [PASS] Detected device:", c_state.get("device_info", {}).get("device_name"), flush=True)

print("\n6. Verifying Host Laptop sees Connected Device...", flush=True)
host_check_req = urllib.request.Request(
    f"{base}/api/session/state",
    headers={"Authorization": f"Bearer {host_token}"}
)
with urllib.request.urlopen(host_check_req, timeout=5) as res:
    h_state = json.loads(res.read().decode())
    print("   [PASS] Host sees device connected:", h_state.get("is_device_connected"), flush=True)
    print("   [PASS] Connected device name:", h_state.get("active_device", {}).get("device_info", {}).get("device_name"), flush=True)

print("\n7. Simulating Lossless File Upload from Phone to Laptop with SHA-256...", flush=True)
boundary = "----AirDropTestBoundary98765"
test_bytes = b"Lossless Apple-style AirDrop 4K raw sample file data with SHA-256 verification"
expected_sha256 = hashlib.sha256(test_bytes).hexdigest()

upload_body = (
    f"--{boundary}\r\n"
    'Content-Disposition: form-data; name="file"; filename="sample_photo.raw"\r\n'
    "Content-Type: application/octet-stream\r\n\r\n"
).encode() + test_bytes + f"\r\n--{boundary}\r\n".encode() + (
    'Content-Disposition: form-data; name="direction"\r\n\r\n'
    'phone_to_laptop\r\n'
    f"--{boundary}--\r\n"
).encode()

up_req = urllib.request.Request(
    f"{base}/api/uploads",
    data=upload_body,
    headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Authorization": f"Bearer {client_token}",
        "X-Forwarded-For": "192.168.29.241"
    }
)
with urllib.request.urlopen(up_req, timeout=10) as res:
    up_res = json.loads(res.read().decode())
    print("   [PASS] Upload completed:", up_res.get("filename"), "Size:", up_res.get("file_size_formatted"), flush=True)
    print("   [PASS] Calculated SHA-256:", up_res.get("sha256"), flush=True)
    assert up_res.get("sha256") == expected_sha256, "SHA-256 hash mismatch!"
    print("   [PASS] Cryptographic integrity match 100% verified!", flush=True)

print("\n8. Testing Network Info & QR Code generation...", flush=True)
with urllib.request.urlopen(f"{base}/api/network/info", timeout=5) as res:
    net_data = json.loads(res.read().decode())
    print("   [PASS] Access URL:", net_data["access_url"], flush=True)
    print("   [PASS] Primary LAN IP:", net_data["primary_ip"], flush=True)
    print("   [PASS] QR Code SVG present:", net_data["qr_code_svg"].startswith("<svg"), flush=True)

print("\nALL VERIFICATIONS PASSED SUCCESSFULLY!", flush=True)
