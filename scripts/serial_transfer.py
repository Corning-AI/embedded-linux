"""Transfer files to i.MX8MP EVK via serial console (COM5).

Uses base64 + heredoc to send binary files over the debug UART.
115200 baud ≈ 11.5 KB/s → ~4MB file takes ~8 minutes.
"""

import serial
import base64
import hashlib
import time
import sys


def transfer_file(ser, local_path, remote_path):
    """Transfer a single file via base64 heredoc."""
    with open(local_path, "rb") as f:
        data = f.read()

    b64 = base64.b64encode(data).decode("ascii")
    md5_expected = hashlib.md5(data).hexdigest()
    total = len(b64)

    print(f"Transferring {local_path} → {remote_path}")
    print(f"  Original: {len(data)} bytes, Base64: {total} bytes, MD5: {md5_expected}")

    # Start heredoc: base64 -d writes decoded binary to remote_path
    cmd = f"base64 -d > {remote_path} << 'ENDOFFILE'\n"
    ser.write(cmd.encode())
    time.sleep(0.5)
    ser.read(ser.in_waiting)

    # Send base64 data in 76-char lines (standard base64 line length)
    start = time.time()
    sent = 0
    line_count = 0

    for i in range(0, total, 76):
        line = b64[i : i + 76] + "\n"
        ser.write(line.encode())
        sent += len(line)
        line_count += 1

        # Every 200 lines (~15KB), pause briefly to avoid UART overflow
        if line_count % 200 == 0:
            time.sleep(0.1)
            ser.read(ser.in_waiting)  # drain echo buffer
            elapsed = time.time() - start
            pct = sent / total * 100
            speed = sent / elapsed / 1024 if elapsed > 0 else 0
            print(f"\r  {pct:5.1f}%  {sent//1024:>5}KB / {total//1024}KB  "
                  f"{speed:.1f} KB/s  {elapsed:.0f}s", end="", flush=True)

    # End heredoc
    ser.write(b"ENDOFFILE\n")
    elapsed = time.time() - start
    print(f"\r  100.0%  {total//1024:>5}KB / {total//1024}KB  "
          f"Done in {elapsed:.0f}s                    ")

    # Wait for base64 decode to finish
    time.sleep(3)
    ser.read(ser.in_waiting)

    # Verify
    ser.write(f"ls -la {remote_path} && md5sum {remote_path}\n".encode())
    time.sleep(3)
    output = ser.read(ser.in_waiting).decode(errors="replace")
    print(f"  Board output: {output.strip()}")
    print(f"  Expected MD5: {md5_expected}")

    if md5_expected in output:
        print("  ✓ Transfer verified OK!")
        return True
    else:
        print("  ✗ MD5 mismatch or verification failed")
        return False


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "COM5"
    print(f"Opening {port} at 115200...")

    ser = serial.Serial(port, 115200, timeout=5)
    time.sleep(0.2)
    ser.read(ser.in_waiting)

    # Create target directory
    ser.write(b"mkdir -p /opt/models\n")
    time.sleep(1)
    ser.read(ser.in_waiting)

    # Disable echo to double throughput
    ser.write(b"stty -echo\n")
    time.sleep(0.5)
    ser.read(ser.in_waiting)

    try:
        # Transfer model
        # Windows paths (downloaded via curl in Git Bash /tmp → AppData\Local\Temp)
        temp = r"C:\Users\corni\AppData\Local\Temp"
        transfer_file(ser, f"{temp}\\detect.tflite", "/opt/models/detect.tflite")

        # Transfer labels (tiny file)
        transfer_file(ser, f"{temp}\\labelmap.txt", "/opt/models/labelmap.txt")

    finally:
        # Always re-enable echo
        ser.write(b"stty echo\n")
        time.sleep(0.5)
        ser.read(ser.in_waiting)
        ser.close()
        print("\nDone. Serial closed.")


if __name__ == "__main__":
    main()
