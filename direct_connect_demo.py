#!/usr/bin/env python3
"""AWS Direct Connect demo — inventory, VIF + BGP health, resiliency, cost.

Usage:
    python direct_connect_demo.py --demo            # offline walkthrough (no AWS needed)
    python direct_connect_demo.py --inventory       # list connections + LAGs (real AWS)
    python direct_connect_demo.py --vifs            # list VIFs and BGP peer status (real AWS)
    python direct_connect_demo.py --resiliency      # check setup against the 99.99% SLA
    python direct_connect_demo.py --cost 1200       # egress cost estimate for N GB/month

Real mode needs AWS credentials with directconnect:Describe* permissions.
"""

import argparse
import json
import os
import sys

REGION = os.environ.get("AWS_REGION", "ap-southeast-1")

# AWS list prices (approx., ap-southeast-1, Nov 2026 — verify before budgeting)
PORT_HOURLY = {"1 Gbps": 0.30, "10 Gbps": 2.25, "100 Gbps": 22.50}
DX_EGRESS_PER_GB = 0.02      # Direct Connect data transfer out
INTERNET_EGRESS_PER_GB = 0.09  # first 10 TB over the internet, approx.


# ---------------------------------------------------------------------------
# Demo data (offline mode — mirrors what the real API returns)
# ---------------------------------------------------------------------------
DEMO_CONNECTIONS = [
    {"connectionId": "dxcon-aaa111", "connectionName": "prod-dx-primary",
     "connectionState": "available", "bandwidth": "10 Gbps",
     "location": "Equinix SG1", "lagId": "dxlag-aaa111"},
    {"connectionId": "dxcon-bbb222", "connectionName": "prod-dx-secondary",
     "connectionState": "available", "bandwidth": "10 Gbps",
     "location": "Digital Realty SIN10", "lagId": None},
]

DEMO_LAGS = [
    {"lagId": "dxlag-aaa111", "lagName": "prod-lag-01", "lagState": "available",
     "connectionsBandwidth": "10 Gbps", "numberOfConnections": 1,
     "minimumLinks": 0},
]

DEMO_VIFS = [
    {"virtualInterfaceId": "dxvif-aaa111", "virtualInterfaceName": "prod-transit-vif",
     "virtualInterfaceType": "transit", "connectionId": "dxcon-aaa111",
     "virtualInterfaceState": "available", "vlan": 100, "asn": 65001,
     "bgpPeers": [{"bgpStatus": "up", "awsDeviceV2": "dxcon-aaa111",
                   "awsLogicalDeviceId": "dxvif-aaa111",
                   "advertisedPrefixes": ["10.0.0.0/8"]}]},
    {"virtualInterfaceId": "dxvif-bbb222", "virtualInterfaceName": "prod-transit-vif-2",
     "virtualInterfaceType": "transit", "connectionId": "dxcon-bbb222",
     "virtualInterfaceState": "available", "vlan": 200, "asn": 65001,
     "bgpPeers": [{"bgpStatus": "up", "awsDeviceV2": "dxcon-bbb222",
                   "awsLogicalDeviceId": "dxvif-bbb222",
                   "advertisedPrefixes": ["10.0.0.0/8"]}]},
    {"virtualInterfaceId": "dxvif-ccc333", "virtualInterfaceName": "prod-public-vif",
     "virtualInterfaceType": "public", "connectionId": "dxcon-aaa111",
     "virtualInterfaceState": "available", "vlan": 300, "asn": 65001,
     "bgpPeers": [{"bgpStatus": "up", "awsDeviceV2": "dxcon-aaa111",
                   "awsLogicalDeviceId": "dxvif-ccc333",
                   "advertisedPrefixes": ["203.0.113.0/24"]}]},
]

DEMO_GATEWAYS = [
    {"directConnectGatewayId": "dxgw-aaa111", "directConnectGatewayName": "prod-dx-gw",
     "directConnectGatewayState": "available", "amazonSideAsn": 64512},
]


def demo_inventory() -> None:
    print("== Connections (demo) ==")
    for c in DEMO_CONNECTIONS:
        lag = f"  LAG {c['lagId']}" if c["lagId"] else "  (no LAG)"
        print(f"  ✅ {c['connectionId']}  {c['connectionName']}  {c['bandwidth']}  "
              f"@ {c['location']}  state={c['connectionState']}{lag}")
    print("== LAGs (demo) ==")
    for lag in DEMO_LAGS:
        print(f"  {lag['lagId']}  {lag['lagName']}  {lag['numberOfConnections']} connection(s)  "
              f"state={lag['lagState']}")
    print("== Direct Connect Gateways (demo) ==")
    for gw in DEMO_GATEWAYS:
        print(f"  {gw['directConnectGatewayId']}  {gw['directConnectGatewayName']}  "
              f"Amazon ASN {gw['amazonSideAsn']}  state={gw['directConnectGatewayState']}")


def demo_vifs() -> None:
    print("== Virtual Interfaces + BGP (demo) ==")
    for vif in DEMO_VIFS:
        peer = vif["bgpPeers"][0]
        status = "✅" if peer["bgpStatus"] == "up" else "❌"
        print(f"  {status} {vif['virtualInterfaceId']}  {vif['virtualInterfaceName']}  "
              f"type={vif['virtualInterfaceType']}  VLAN {vif['vlan']}  "
              f"BGP={peer['bgpStatus']}  prefixes={peer['advertisedPrefixes']}")
    down = [v for v in DEMO_VIFS if v["bgpPeers"][0]["bgpStatus"] != "up"]
    if down:
        print(f"  ⚠️  {len(down)} BGP peer(s) down — check MD5 auth, ASN, and the VIF VLAN.")


def demo_resiliency() -> None:
    print("== Resiliency check vs the 99.99% SLA (demo) ==")
    locations = {c["location"] for c in DEMO_CONNECTIONS
                 if c["connectionState"] == "available"}
    transit_vifs_up = sum(
        1 for v in DEMO_VIFS
        if v["virtualInterfaceType"] == "transit"
        and v["bgpPeers"][0]["bgpStatus"] == "up")
    checks = [
        ("Two available connections", len(DEMO_CONNECTIONS) >= 2),
        ("Two different DX locations", len(locations) >= 2),
        ("Transit VIF BGP up on both paths", transit_vifs_up >= 2),
        ("Same prefixes advertised on both paths",
         len({tuple(v["bgpPeers"][0]["advertisedPrefixes"])
              for v in DEMO_VIFS
              if v["virtualInterfaceType"] == "transit"}) == 1),
    ]
    for label, ok in checks:
        print(f"  {'✅' if ok else '❌'} {label}")
    if all(ok for _, ok in checks):
        print("  🎉 Qualifies for the 99.99% SLA (two locations, redundant BGP).")
        print("  👉 Still verify BFD is enabled and run a real failover test —")
        print("     an untested redundant path is a rumour, not a backup.")
    else:
        print("  ⚠️  Currently 99.9% at best — add a second connection at a")
        print("     DIFFERENT DX location with matching BGP advertisements.")


def demo_cost(egress_gb: float) -> None:
    print(f"== Monthly cost estimate (demo) — {egress_gb:,.0f} GB egress ==")
    port = 2 * PORT_HOURLY["10 Gbps"] * 730  # two 10 Gbps connections, redundant pair
    dx_egress = egress_gb * DX_EGRESS_PER_GB
    internet_egress = egress_gb * INTERNET_EGRESS_PER_GB
    print(f"  Port hours (2 × 10 Gbps):  ${port:,.2f}")
    print(f"  DX egress ({egress_gb:,.0f} GB @ ${DX_EGRESS_PER_GB}/GB):  ${dx_egress:,.2f}")
    print(f"  DX total:                  ${port + dx_egress:,.2f}")
    print(f"  Internet egress (same GB): ${internet_egress:,.2f}")
    saving = internet_egress - (port + dx_egress)
    if saving > 0:
        print(f"  💰 DX saves ~${saving:,.2f}/month at this volume — the port pays for itself.")
    else:
        print(f"  ⚠️  DX costs ~${-saving:,.2f}/month MORE at this volume —")
        print("     a VPN may be cheaper until egress grows. DX still buys")
        print("     stable latency and a private path, which a VPN cannot.")


def demo() -> None:
    print("AWS Direct Connect — offline demo (no AWS calls)\n")
    demo_inventory()
    print()
    demo_vifs()
    print()
    demo_resiliency()
    print()
    demo_cost(1200)
    print("\nDone. Run with --inventory / --vifs / --resiliency against real AWS.")


# ---------------------------------------------------------------------------
# Real AWS mode (boto3)
# ---------------------------------------------------------------------------
def _client():
    import boto3  # noqa: PLC0415  (only needed for real mode)
    return boto3.client("directconnect", region_name=REGION)


def real_inventory() -> None:
    dx = _client()
    for c in dx.describe_connections()["connections"]:
        print(f"  {c['connectionId']}  {c['connectionName']}  {c['bandwidth']}  "
              f"@ {c['location']}  state={c['connectionState']}")
    for lag in dx.describe_lags()["lags"]:
        print(f"  LAG {lag['lagId']}  {lag['lagName']}  "
              f"{lag['numberOfConnections']} connection(s)  state={lag['lagState']}")
    for gw in dx.describe_direct_connect_gateways()["directConnectGateways"]:
        print(f"  DXGW {gw['directConnectGatewayId']}  {gw['directConnectGatewayName']}  "
              f"Amazon ASN {gw['amazonSideAsn']}")


def real_vifs() -> None:
    dx = _client()
    for vif in dx.describe_virtual_interfaces()["virtualInterfaces"]:
        peers = vif.get("bgpPeers", [])
        bgp = peers[0].get("bgpStatus", "?") if peers else "no peer"
        print(f"  {vif['virtualInterfaceId']}  {vif['virtualInterfaceName']}  "
              f"type={vif['virtualInterfaceType']}  VLAN {vif['vlan']}  BGP={bgp}")


def real_resiliency() -> None:
    dx = _client()
    connections = [c for c in dx.describe_connections()["connections"]
                   if c["connectionState"] == "available"]
    locations = {c["location"] for c in connections}
    vifs = dx.describe_virtual_interfaces()["virtualInterfaces"]
    transit_up = sum(1 for v in vifs
                     if v["virtualInterfaceType"] == "transit"
                     and v.get("bgpPeers")
                     and v["bgpPeers"][0].get("bgpStatus") == "up")
    checks = [
        ("Two available connections", len(connections) >= 2),
        ("Two different DX locations", len(locations) >= 2),
        ("Transit VIF BGP up on both paths", transit_up >= 2),
    ]
    for label, ok in checks:
        print(f"  {'✅' if ok else '❌'} {label}")
    print("  Qualifies for 99.99% SLA." if all(ok for _, ok in checks)
          else "  Currently 99.9% at best — see README resiliency section.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="offline walkthrough")
    parser.add_argument("--inventory", action="store_true")
    parser.add_argument("--vifs", action="store_true")
    parser.add_argument("--resiliency", action="store_true")
    parser.add_argument("--cost", type=float, metavar="GB",
                        help="egress cost estimate for GB/month")
    args = parser.parse_args(argv)

    if args.demo:
        demo()
        return 0
    if args.inventory:
        real_inventory()
        return 0
    if args.vifs:
        real_vifs()
        return 0
    if args.resiliency:
        real_resiliency()
        return 0
    if args.cost is not None:
        demo_cost(args.cost)
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
