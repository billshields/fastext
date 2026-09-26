"""Fetch web pages for URL import without letting users reach internal addresses (SSRF).

Every socket the fetcher opens, whether for the first request, a redirect, or a
request cloudscraper makes to solve a Cloudflare challenge, resolves the
hostname once, rejects it unless every address is public, and then connects to
one of those checked addresses. Connecting to the checked address instead of
the hostname stops a DNS answer that changes between the check and the connect
(DNS rebinding). TLS still verifies the certificate against the hostname.
"""
import ipaddress
import socket
import time

import cloudscraper
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.exceptions import ConnectTimeoutError, NameResolutionError, NewConnectionError

MAX_RESPONSE_BYTES = 10 * 1024 * 1024
MAX_REDIRECTS = 5
TIMEOUT = (5, 15)  # connect, read; each applies per socket operation
DEADLINE_SECONDS = 30  # for reading bodies, however slowly the server sends them

# IPv6 ranges that carry an IPv4 address in their last 32 bits
EMBEDDED_IPV4_NETWORKS = (
    ipaddress.ip_network('::ffff:0:0/96'),  # IPv4-mapped
    ipaddress.ip_network('::/96'),  # IPv4-compatible (deprecated)
    ipaddress.ip_network('64:ff9b::/96'),  # NAT64
)


class FetchError(Exception):
    """A fetch failure whose message is safe to show the user."""


class BlockedAddressError(FetchError):
    pass


class ResponseTooLargeError(FetchError):
    pass


def is_public_ip(address):
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if ip.version == 6 and any(ip in network for network in EMBEDDED_IPV4_NETWORKS):
        ip = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    # is_global counts multicast as global
    return ip.is_global and not ip.is_multicast


def resolve_public_addresses(host, port):
    """Resolve host, and raise unless every address it resolves to is public."""
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    addresses = list(dict.fromkeys(info[4][0] for info in infos))
    if not all(is_public_ip(address) for address in addresses):
        raise BlockedAddressError('This URL points to a private or local network address, so it can\'t be imported.')
    return addresses


class PublicAddressMixin:
    def _new_conn(self):
        try:
            addresses = resolve_public_addresses(self._dns_host, self.port)
        except socket.gaierror as e:
            raise NameResolutionError(self.host, self, e) from e

        # urllib3 connects to _dns_host; TLS uses self.host, which stays the hostname
        hostname = self._dns_host
        try:
            for address in addresses:
                self._dns_host = address
                try:
                    return super()._new_conn()
                except (NewConnectionError, ConnectTimeoutError) as e:
                    error = e
            raise error
        finally:
            self._dns_host = hostname


class PublicHTTPConnection(PublicAddressMixin, HTTPConnection):
    pass


class PublicHTTPSConnection(PublicAddressMixin, HTTPSConnection):
    pass


class PublicHTTPConnectionPool(HTTPConnectionPool):
    ConnectionCls = PublicHTTPConnection


class PublicHTTPSConnectionPool(HTTPSConnectionPool):
    ConnectionCls = PublicHTTPSConnection


def read_body(response, deadline):
    """Read the whole body up front, within the size and time limits.

    This runs as a response hook, so it also covers redirect responses and the
    ones cloudscraper inspects for challenges. Both would otherwise be read in
    full, however large.
    """
    body = bytearray()
    try:
        # iter_content decompresses, so the cap also stops compression bombs
        for chunk in response.iter_content(64 * 1024):
            body += chunk
            if len(body) > MAX_RESPONSE_BYTES:
                raise ResponseTooLargeError('This page is too large to import.')
            if time.monotonic() > deadline:
                raise FetchError('The site took too long to respond.')
    except BaseException:
        response.close()
        raise
    response._content = bytes(body)


def fetch_page(url):
    """Download url and return the body as bytes.

    Raises FetchError for problems to report to the user as is, and
    requests.HTTPError for error statuses. Anything else is a
    requests or cloudscraper exception.
    """
    deadline = time.monotonic() + DEADLINE_SECONDS
    with cloudscraper.create_scraper() as scraper:
        # A proxy from the environment would open the connection itself, skipping the address check
        scraper.trust_env = False
        scraper.max_redirects = MAX_REDIRECTS
        for adapter in scraper.adapters.values():
            adapter.poolmanager.pool_classes_by_scheme = {
                'http': PublicHTTPConnectionPool,
                'https': PublicHTTPSConnectionPool,
            }
        scraper.hooks['response'].append(lambda response, **kwargs: read_body(response, deadline))

        response = scraper.get(url, timeout=TIMEOUT, stream=True)
        response.raise_for_status()
        return response.content
