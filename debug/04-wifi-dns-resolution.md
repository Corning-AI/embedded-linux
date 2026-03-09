# WiFi connected but DNS resolution fails

## Symptom

Board connects to WiFi successfully via `mlan0`, gets an IP address, and can ping external IPs, but any hostname-based access fails:

```
root@imx8mpevk:~# ip addr show mlan0 | grep inet
    inet 192.168.1.98/24 brd 192.168.1.255 scope global mlan0

root@imx8mpevk:~# ping -c 1 8.8.8.8
64 bytes from 8.8.8.8: icmp_seq=1 ttl=104 time=11.0 ms

root@imx8mpevk:~# wget https://example.com
Resolving example.com... failed: Name or service not known.
```

IP connectivity works, but DNS doesn't.

## Root cause

`/etc/resolv.conf` is empty or doesn't exist. The WiFi association was done manually (or via `wpa_supplicant` without a DHCP client that writes resolv.conf). The IP was obtained via DHCP but the DNS server addresses from the DHCP response weren't written to resolv.conf.

On full desktop distributions, `systemd-resolved` or `NetworkManager` handles this automatically. On minimal Yocto images, there's often no daemon managing resolv.conf.

## Fix

```bash
echo "nameserver 8.8.8.8" > /etc/resolv.conf
```

For persistence across reboots, add it to a startup script or configure the DHCP client to update resolv.conf. With `udhcpc` (BusyBox):

```bash
# udhcpc's default script should handle this, but verify:
cat /usr/share/udhcpc/default.script | grep resolv
```

## Verification

```
root@imx8mpevk:~# ping -c 1 storage.googleapis.com
PING storage.googleapis.com (74.125.130.207) 56(84) bytes of data.
64 bytes from sb-in-f207.1e100.net: icmp_seq=1 ttl=104 time=9.26 ms
```

## Additional note

Long URLs sent over the 115200 baud debug UART tend to get corrupted (duplicate characters from echo timing). Workaround: build the URL in parts using shell variables, or use `python3 -c "import urllib.request; ..."` on the board where the URL is a string literal processed locally.
