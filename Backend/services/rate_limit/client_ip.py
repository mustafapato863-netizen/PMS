"""Client address used as the rate-limit subject for unauthenticated traffic.

Behind the gateway every request arrives from the gateway's own address, so the
real client only appears in X-Forwarded-For. That header is honored only when
the direct peer is a trusted proxy, and then only the right-most hop that is not
itself a trusted proxy is used. A value added by the client sits to the left of
the hop the gateway appended, so it cannot be chosen.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable, Sequence

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network

UNKNOWN_ADDRESS = "unknown"


def parse_trusted_networks(values: Iterable[str]) -> tuple[IPNetwork, ...]:
    return tuple(
        ipaddress.ip_network(value.strip(), strict=False)
        for value in values
        if value.strip()
    )


def _parse_ip(text: str) -> IPAddress | None:
    try:
        address = ipaddress.ip_address(text.strip())
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def _is_trusted(address: IPAddress, trusted: Sequence[IPNetwork]) -> bool:
    return any(address.version == network.version and address in network for network in trusted)


def client_address(peer: str | None, forwarded_for: str | None, trusted: Sequence[IPNetwork]) -> str:
    """Return the address to rate limit by. Never raises.

    A malformed or missing header falls back to the direct peer. When every hop
    is a trusted proxy, the left-most hop is returned.
    """
    peer_text = (peer or "").strip() or UNKNOWN_ADDRESS
    peer_ip = _parse_ip(peer_text)
    if peer_ip is None:
        return peer_text
    peer_address = str(peer_ip)
    if not _is_trusted(peer_ip, trusted) or not forwarded_for:
        return peer_address

    hops = [_parse_ip(part) for part in forwarded_for.split(",")]
    if any(hop is None for hop in hops):
        return peer_address
    for hop in reversed(hops):
        if not _is_trusted(hop, trusted):
            return str(hop)
    return str(hops[0])
