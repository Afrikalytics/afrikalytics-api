"""
Configuration du rate limiter (SlowAPI).
Extrait de main.py pour etre importable par les routers sans import circulaire.

Uses a custom key_func to extract the real client IP from proxy headers
(X-Forwarded-For, X-Real-IP) instead of the default request.client.host
which returns the reverse proxy IP when running behind Railway/Nginx.
"""

import ipaddress
import logging

from starlette.requests import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)

# Private/reserved IP ranges used by reverse proxies (Railway, Nginx, Docker, etc.)
# Only trust X-Forwarded-For when the direct connection comes from one of these.
_TRUSTED_PROXY_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),       # RFC 1918 — private (Docker, Railway internal)
    ipaddress.ip_network("172.16.0.0/12"),     # RFC 1918 — private (Docker default)
    ipaddress.ip_network("192.168.0.0/16"),    # RFC 1918 — private (local networks)
    ipaddress.ip_network("127.0.0.0/8"),       # loopback
    ipaddress.ip_network("::1/128"),           # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),          # IPv6 unique local
    ipaddress.ip_network("fe80::/10"),         # IPv6 link-local
]


def _is_trusted_proxy(ip: str) -> bool:
    """Check if an IP belongs to a trusted proxy network."""
    try:
        addr = ipaddress.ip_address(ip)
        return any(addr in network for network in _TRUSTED_PROXY_NETWORKS)
    except ValueError:
        return False


def get_real_client_ip(request: Request) -> str:
    """Extract the real client IP from proxy headers.

    Strategy:
    1. If the direct connection (request.client.host) is from a trusted proxy,
       check X-Forwarded-For and X-Real-IP headers.
    2. X-Forwarded-For contains a chain: "client, proxy1, proxy2".
       We walk from the RIGHT and return the first non-trusted-proxy IP
       (the rightmost entry that isn't an internal proxy).
    3. If X-Forwarded-For is absent or all entries are trusted proxies,
       fall back to X-Real-IP.
    4. If no proxy headers are present, use the direct connection IP.

    This approach prevents IP spoofing: an attacker can prepend fake IPs to
    X-Forwarded-For, but the rightmost non-proxy IP was added by the last
    trusted proxy and represents the real client.
    """
    direct_ip = get_remote_address(request)

    # If not behind a trusted proxy, don't trust forwarded headers at all
    if not _is_trusted_proxy(direct_ip):
        return direct_ip

    # Try X-Forwarded-For first (standard proxy header)
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        # Parse the chain: "client_ip, proxy1_ip, proxy2_ip"
        ips = [ip.strip() for ip in forwarded_for.split(",") if ip.strip()]
        # Walk from rightmost to leftmost, skip trusted proxies
        for ip in reversed(ips):
            if not _is_trusted_proxy(ip):
                return ip
        # All IPs in the chain are trusted proxies — unusual but possible
        # Fall through to other headers

    # Try X-Real-IP (set by Nginx, some load balancers)
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()

    # Fallback: use direct connection IP
    return direct_ip


limiter = Limiter(key_func=get_real_client_ip)
