# DVR Network Configuration (Static IPv4 Setup via Router)

## Network Topology

The connection is established using the following structure:

```
PC → Router → DVR
```

The router acts as the local network bridge between the computer and the DVR.

This setup allows:

- Stable LAN communication
- Future internet access (if required)
- Multi-device connectivity
- Easier IP management

---

# Why Manual IPv4 Configuration Was Required

The router was operating without internet access and without automatic DHCP assignment configured for the DVR.

To ensure communication between the PC and the DVR:

- Both devices must belong to the same subnet.
- The router must be in the same IP range.
- All devices must share the same subnet mask.

Example network configuration:

| Device  | IP Address       |
|----------|------------------|
| Router   | 192.168.1.1      |
| DVR      | 192.168.1.108    |
| PC       | 192.168.1.50     |

Subnet mask (all devices):

```
255.255.255.0
```

The key requirement is that all devices share:

```
192.168.1.X
```

---

# Step 1 – Configure the Router

1. Connect the PC to the router.
2. Access the router panel (usually):
   ```
   http://192.168.1.1
   ```
3. Verify:
   - LAN IP range
   - DHCP settings
4. Ensure the router LAN IP matches the DVR subnet.

If DHCP is enabled:
- The PC may receive an IP automatically.
- The DVR may need manual configuration.

If DHCP is disabled:
- Both PC and DVR must be configured manually.

---

# Step 2 – Configure the DVR

Inside the DVR network settings:

- Set a static IP within the router's LAN range.
- Avoid IP conflicts.
- Use the router IP as gateway (optional but recommended).

Example:

```
IP Address: 192.168.1.108
Subnet Mask: 255.255.255.0
Gateway: 192.168.1.1
DNS: 8.8.8.8 (optional)
```

---

# Step 3 – Configure the PC

The PC must be in the same subnet.

## Windows Configuration

1. Open:
   ```
   Control Panel → Network and Internet → Network Connections
   ```
2. Right-click the active Ethernet adapter.
3. Select:
   ```
   Properties → Internet Protocol Version 4 (TCP/IPv4)
   ```
4. Select:
   ```
   Use the following IP address
   ```
5. Set:

```
IP Address: 192.168.1.50
Subnet Mask: 255.255.255.0
Gateway: 192.168.1.1
```

Click OK and save.

---

## macOS Configuration

1. Open:
   ```
   System Settings → Network
   ```
2. Select the active network interface (Ethernet or Wi-Fi).
3. Click:
   ```
   Details → TCP/IP
   ```
4. Configure IPv4 manually.
5. Set:

```
IP Address: 192.168.1.50
Subnet Mask: 255.255.255.0
Router: 192.168.1.1
```

Apply changes.

---

## Ubuntu (Linux) Configuration

### Option A – GUI Method

1. Open:
   ```
   Settings → Network
   ```
2. Select the active interface.
3. Click:
   ```
   IPv4 → Manual
   ```
4. Enter:

```
Address: 192.168.1.50
Netmask: 255.255.255.0
Gateway: 192.168.1.1
DNS: 8.8.8.8
```

Apply and reconnect.

---

### Option B – Netplan (CLI Configuration)

Edit the netplan file:

```
sudo nano /etc/netplan/01-network-manager-all.yaml
```

Example configuration:

```yaml
network:
  version: 2
  renderer: NetworkManager
  ethernets:
    enp3s0:
      dhcp4: no
      addresses:
        - 192.168.1.50/24
      gateway4: 192.168.1.1
      nameservers:
        addresses: [8.8.8.8]
```

Apply changes:

```
sudo netplan apply
```

---

# Step 4 – Verify Connectivity

From the PC:

Ping the DVR:

```
ping 192.168.1.108
```

If successful, test RTSP stream:

Example:

```
rtsp://username:password@192.168.1.108:554/cam/realmonitor?channel=1&subtype=0
```

You can test with:

- VLC
- ONVIF Device Manager
- FFmpeg

---

# Key Networking Principles Applied

- Same subnet for all devices
- Static IP for DVR (recommended for stability)
- Router acting as LAN bridge
- Avoid IP conflicts
- Gateway set to router LAN IP

---

# Why This Configuration Is Important

This network setup guarantees:

- Stable communication between PC and DVR
- Proper RTSP stream access
- Predictable IP addressing
- Simplified debugging
- Future scalability for multiple cameras

The configuration ensures that the AI system can reliably access video streams inside a controlled LAN environment.
