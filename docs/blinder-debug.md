# Cameo Matrix 300 Blinder Debug Analysis

Date: 2026-04-12

## Hardware Setup

- 2x Cameo Matrix 300 (5x5 RGB, 25 pixels each)
- Resolume DmxScreen "MATRIX 300 RGB" on LumiverseId 19
- Output to Enttec ODE Mk2 (Art-Net node ID 3388997634)
- Subnet 1, Universe 14
- Blinder 1 (right): DMX channels 4-78 (25 pixels x 3 channels)
- Blinder 2 (left): DMX channels 101-175 (25 pixels x 3 channels)
- Channels 1-3: likely global dimmer/mode

## Network Topology

| Address Range    | MAC Prefix | Device Type              | Count |
|------------------|------------|--------------------------|-------|
| 2.0.0.11-22      | 00:50:c2   | Enttec Pixel Octo strips | 12    |
| 2.0.0.201-202    | 00:50:c2   | Enttec ODE Mk2 (likely)  | 2     |
| 169.254.x.x      | 00:1d:c1   | Unknown (link-local)     | ?     |
| 2.0.0.5          | --         | Dell (Resolume host)     | 1     |

The 00:50:c2 MAC prefix is Enttec. The 00:1d:c1 prefix is also Enttec
(older ODE range). The 169.254.x.x addresses are link-local/APIPA,
meaning those nodes either have no static IP configured or failed DHCP.

## Test Results Summary

| # | Target Nodes       | Universe(s)  | Right Blinder | Left Blinder       |
|---|-------------------|--------------|---------------|--------------------|
| 1 | ALL 14 nodes       | S1:U14       | Blinks pink   | Blinks pink        |
| 2 | 201+202 only       | S1:U14       | ON (steady)   | OFF                |
| 3 | 11-22 individually | S1:U14       | OFF           | OFF                |
| 4 | 11-22 all at once  | S1:U14       | OFF           | OFF                |
| 5 | 169.254.x.x only   | S1:U14       | OFF           | OFF                |
| 6 | 201+202 only       | S1:U14+U15   | Blinks pink   | Blue (steady?)     |
| 7 | ALL nodes          | All 32 unis  | Blinks pink   | Blinks pink        |
| 8 | (state test)       | S1:U14       | Holds state   | Always blinks      |
| 9 | ALL nodes 20fps    | S1:U14       | Steady        | Still blinks       |

## Analysis

### Q1: What Art-Net node controls the left blinder?

**Most likely: one of the 169.254.x.x nodes (MAC 00:1d:c1).**

Evidence:
- The right blinder is confirmed on the ODE Mk2 at 2.0.0.201/202, subnet 1 uni 14.
- The left blinder does NOT respond when targeting only 201+202 (test 2).
- The left blinder does NOT respond when targeting only 11-22 (tests 3, 4).
- The left blinder DOES respond when ALL nodes are targeted (tests 1, 7).
- The only remaining nodes are the 169.254.x.x ones.
- Yet targeting 169.254.x.x directly produced nothing (test 5).

This apparent contradiction is explained by Art-Net broadcast behavior.
When sending to ALL nodes, the test script likely used broadcast
(2.255.255.255 or 255.255.255.255). The 169.254.x.x nodes sit on a
different subnet, so unicast from 2.0.0.5 will not reach them. But
broadcast on the physical LAN segment reaches all devices regardless of
IP subnet, as long as they share the same Ethernet segment (same switch
or VLAN).

**The left blinder is almost certainly connected through a 169.254.x.x
node that only receives Art-Net via broadcast, not unicast.**

This also explains why test 5 (unicast to 169.254.x.x from 2.0.0.5)
failed: the host at 2.0.0.5/8 cannot route unicast packets to
169.254.x.x/16 without an explicit route or a second interface on that
subnet.

### Q2: Why does the left blinder only work when ALL nodes receive data?

Because "send to all nodes" uses **broadcast packets** that reach every
device on the physical LAN segment. The 169.254.x.x node controlling
the left blinder sits on a different IP subnet than the Dell (2.0.0.x).
Unicast packets from 2.0.0.5 to 169.254.x.x get dropped at the IP
layer (no route, different subnet). But Ethernet broadcast frames
(destination ff:ff:ff:ff:ff:ff) are delivered to all ports on the switch,
so the node receives them.

The Art-Net spec supports broadcast delivery (default for Art-Net I/II).
Many Art-Net implementations fall back to broadcast when the target
isn't specified. When the test script iterated individual node IPs, it
used unicast, which the cross-subnet node never received.

### Q3: Why does the left blinder blink instead of holding state?

Two likely factors:

1. **Art-Net timeout / loss-of-signal behavior.** Many Art-Net nodes
   (especially Enttec ODE models) implement a configurable timeout: if
   no Art-Net data is received for N seconds (often 3-10s), the node
   blacks out or enters a failsafe state. The right blinder (ODE Mk2 at
   201/202) is on the same subnet as the sender and receives every
   packet reliably, so it holds state. The left blinder only receives
   broadcast frames, which may be sent less reliably or may arrive
   intermittently due to:
   - Broadcast throttling by the switch or OS
   - Packet drops from rate limiting on broadcast traffic
   - The node's Art-Net stack resetting between bursts

2. **ArtPollReply / subscription mismatch.** Art-Net III uses directed
   (unicast) transmission to nodes that have responded to ArtPoll. If
   the test script or Resolume sends ArtPoll, the 169.254.x.x node's
   reply may never reach back (different subnet, no route). Without a
   valid subscription, the node only gets data when broadcast happens to
   include it, causing intermittent reception that looks like blinking.

The blinking pattern (on-off-on-off) is consistent with receiving data
during broadcast bursts, then timing out between them.

### Q4: Most likely fix

**Give the left blinder's Art-Net node a static IP on the 2.0.0.x subnet.**

Steps:

1. **Identify the node.** Physically trace the DMX cable from the left
   blinder back to its Art-Net node. It should be one of the 169.254.x.x
   devices (MAC 00:1d:c1). If it is an older Enttec ODE, it may have
   DIP switches or a web config interface.

2. **Assign a 2.0.0.x address.** Options:
   - If the node has a web interface, temporarily add a 169.254.x.x
     alias to the Dell's NIC (`ip addr add 169.254.1.1/16 dev <iface>`)
     to access the config page, then set a static IP like 2.0.0.203.
   - If the node uses DIP switches, set the address directly.
   - Enttec NMU (Node Management Utility) can also reconfigure nodes
     if it can see them via broadcast.

3. **Verify universe config.** Once reachable by unicast, confirm the
   node is set to subnet 1, universe 14 (matching Resolume). Test 6
   showed the left blinder responded to universe 15 data with the wrong
   color, suggesting the node might currently be configured for universe
   15 instead of 14, or the pixel mapping straddles the universe
   boundary.

4. **Check universe assignment.** The left blinder uses DMX channels
   101-175. If Resolume is configured for a single universe (uni 14),
   all 175 channels fit within one 512-channel universe. But if the
   actual node is set to universe 15, it would interpret channel 101-175
   data as starting from a different offset. The blue response in test 6
   confirms data IS reaching the node but with a universe/channel
   mismatch. Verify:
   - Node's configured start universe matches Resolume's output universe
   - Node's DMX start address is 1 (not offset)

5. **Test.** After IP and universe config, send unicast Art-Net to the
   node's new 2.0.0.x address on subnet 1, universe 14. The left
   blinder should respond steadily without blinking.

## Quick Diagnostic Checklist

- [ ] Trace left blinder's DMX cable to its Art-Net node
- [ ] Confirm node's MAC address (expect 00:1d:c1:xx:xx:xx)
- [ ] Add temporary 169.254.x.x alias to Dell NIC to reach the node
- [ ] Access node's web config and note current IP + universe settings
- [ ] Set node IP to 2.0.0.203 (or next free address on 2.0.0.x)
- [ ] Set node to subnet 1, universe 14, DMX start address 1
- [ ] Remove temporary 169.254.x.x alias from Dell NIC
- [ ] Test unicast Art-Net from Dell to new IP: left blinder should hold steady
- [ ] Update Resolume output config if needed to target the new node IP

## Alternative: Broadcast-only Workaround

If reconfiguring the node is not possible (e.g., no access to its
config interface), Resolume can be set to broadcast Art-Net instead of
unicasting to specific nodes. This is less efficient but ensures all
nodes on the LAN receive data:

- In Resolume: Output > Art-Net > set target to broadcast (2.255.255.255)
- This should make the left blinder work, but the blinking may persist
  if the node's timeout is shorter than the frame interval
- Increase Art-Net output FPS in Resolume to 30-40fps to keep the node
  fed continuously

The proper fix is giving the node a routable IP address on 2.0.0.x.
