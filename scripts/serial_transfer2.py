"""Transfer files to i.MX8MP EVK via serial — Python receiver approach.

Strategy: start a Python receiver on the board, send base64 lines,
send 'END' marker. Much more reliable than heredoc for large files.
"""

import serial
import base64
import hashlib
import time
import sys
import os
import tempfile


def wait_for(ser, marker, timeout=10):
    """Read serial until marker string is found or timeout."""
    start = time.time()
    buf = ""
    while time.time() - start < timeout:
        data = ser.read(ser.in_waiting or 1)
        if data:
            buf += data.decode(errors="replace")
            if marker in buf:
                return buf
    return buf


def transfer_file(ser, local_path, remote_path):
    """Transfer a file using Python receiver on the board."""
    with open(local_path, "rb") as f:
        data = f.read()

    b64 = base64.b64encode(data).decode("ascii")
    md5_expected = hashlib.md5(data).hexdigest()

    # Split into 76-char lines
    lines = [b64[i:i+76] for i in range(0, len(b64), 76)]

    print(f"File: {os.path.basename(local_path)} -> {remote_path}")
    print(f"  Size: {len(data)} bytes, {len(lines)} base64 lines")
    print(f"  Expected MD5: {md5_expected}")

    # Clear any pending data
    ser.read(ser.in_waiting)

    # Start Python receiver on the board
    receiver = (
        f"python3 -c \""
        f"import base64\\n"
        f"d=[]\\n"
        f"while True:\\n"
        f"  l=input()\\n"
        f"  if l.strip()=='END': break\\n"
        f"  d.append(l.strip())\\n"
        f"open('{remote_path}','wb').write(base64.b64decode(''.join(d)))\\n"
        f"print('XFER_OK')\\n"
        f"\""
    )
    ser.write((receiver + "\n").encode())
    time.sleep(1)
    ser.read(ser.in_waiting)  # drain echo of the command

    # Send base64 lines
    start = time.time()
    for i, line in enumerate(lines):
        ser.write((line + "\n").encode())

        # Periodically drain echo buffer and show progress
        if (i + 1) % 500 == 0:
            time.sleep(0.05)
            ser.read(ser.in_waiting)
            elapsed = time.time() - start
            pct = (i + 1) / len(lines) * 100
            speed = (i + 1) * 76 / elapsed / 1024
            eta = (len(lines) - i - 1) * elapsed / (i + 1)
            print(f"\r  {pct:5.1f}%  {i+1}/{len(lines)} lines  "
                  f"{speed:.1f} KB/s  ETA {eta:.0f}s  ", end="", flush=True)

    # Send END marker
    ser.write(b"END\n")
    print(f"\r  100.0%  Sent all {len(lines)} lines. Waiting for decode...", flush=True)

    # Wait for XFER_OK
    result = wait_for(ser, "XFER_OK", timeout=30)
    elapsed = time.time() - start

    if "XFER_OK" in result:
        print(f"  Transfer complete in {elapsed:.0f}s")
    else:
        print(f"  WARNING: did not see XFER_OK. Output: {result[-200:]}")
        return False

    # Wait for shell prompt
    time.sleep(2)
    ser.read(ser.in_waiting)

    # Verify MD5
    ser.write(f"md5sum {remote_path}\n".encode())
    time.sleep(3)
    output = ser.read(ser.in_waiting).decode(errors="replace")
    print(f"  Board MD5: {output.strip()}")

    if md5_expected in output:
        print("  Verified OK!")
        return True
    else:
        print(f"  MD5 mismatch! Expected: {md5_expected}")
        return False


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "COM5"
    temp = tempfile.gettempdir()

    print(f"Opening {port} at 115200...")
    ser = serial.Serial(port, 115200, timeout=3)
    time.sleep(0.2)
    ser.read(ser.in_waiting)

    # Create target directory
    ser.write(b"mkdir -p /opt/models\n")
    time.sleep(1)
    ser.read(ser.in_waiting)

    # Transfer model
    ok1 = transfer_file(ser, f"{temp}\\detect.tflite", "/opt/models/detect.tflite")

    # Transfer labels
    ok2 = transfer_file(ser, f"{temp}\\labelmap.txt", "/opt/models/labelmap.txt")

    ser.close()
    print(f"\nResults: model={'OK' if ok1 else 'FAIL'}, labels={'OK' if ok2 else 'FAIL'}")


if __name__ == "__main__":
    main()
