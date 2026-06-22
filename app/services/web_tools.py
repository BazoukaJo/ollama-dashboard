"""Read-only web tools for Ask? agent mode and MCP (fetch pages, search the web)."""
from __future__ import annotations

import html
import ipaddress
import os
import re
import socket
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse, urlunparse

import requests

_DEFAULT_TIMEOUT = 15
_DEFAULT_MAX_BYTES = 512_000
_DEFAULT_MAX_CHARS = 12_000
_DEFAULT_SEARCH_RESULTS = 5
_USER_AGENT = 'ollama-dashboard-web-tools/1.0'


def mcp_allow_web() -> bool:
    return os.getenv('MCP_ALLOW_WEB', 'true').strip().lower() in ('1', 'true', 'yes', 'on')


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(int(os.getenv(name, str(default))), maximum))
    except (TypeError, ValueError):
        return default


def _fetch_timeout() -> int:
    return _env_int('MCP_WEB_TIMEOUT', _DEFAULT_TIMEOUT, minimum=3, maximum=60)


def _fetch_max_bytes() -> int:
    return _env_int('MCP_WEB_MAX_BYTES', _DEFAULT_MAX_BYTES, minimum=4096, maximum=2_000_000)


def _fetch_max_chars() -> int:
    return _env_int('MCP_WEB_MAX_CHARS', _DEFAULT_MAX_CHARS, minimum=1000, maximum=100_000)


def _search_max_results() -> int:
    return _env_int('MCP_WEB_SEARCH_MAX_RESULTS', _DEFAULT_SEARCH_RESULTS, minimum=1, maximum=10)


def _blocked_hostnames() -> frozenset[str]:
    raw = os.getenv('MCP_WEB_BLOCKED_HOSTS', 'localhost,127.0.0.1,0.0.0.0,::1')
    return frozenset(part.strip().lower() for part in raw.split(',') if part.strip())


def _is_private_ip(value: str) -> bool:
    try:
        addr = ipaddress.ip_address(value)
    except ValueError:
        return True
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def _resolve_host_ips(hostname: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except OSError as err:
        raise ValueError(f'Cannot resolve host {hostname!r}: {err}') from err
    ips: list[str] = []
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        ip = str(sockaddr[0])
        if ip not in ips:
            ips.append(ip)
    if not ips:
        raise ValueError(f'Cannot resolve host {hostname!r}')
    return ips


def _validate_public_http_url(url: str) -> str:
    text = str(url or '').strip()
    if not text:
        raise ValueError('url is required')
    parsed = urlparse(text)
    if parsed.scheme not in ('http', 'https'):
        raise ValueError('Only http and https URLs are allowed')
    hostname = (parsed.hostname or '').strip().lower()
    if not hostname:
        raise ValueError('URL must include a hostname')
    if hostname in _blocked_hostnames():
        raise ValueError(f'Host {hostname!r} is blocked')
    if hostname.endswith('.local') or hostname.endswith('.internal'):
        raise ValueError(f'Host {hostname!r} is blocked')
    for ip in _resolve_host_ips(hostname):
        if _is_private_ip(ip):
            raise ValueError(f'Host {hostname!r} resolves to a private or local address')
    return urlunparse(parsed)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ('script', 'style', 'noscript'):
            self._skip_depth += 1
        elif tag in ('p', 'br', 'div', 'li', 'h1', 'h2', 'h3', 'h4', 'tr'):
            self._chunks.append('\n')

    def handle_endtag(self, tag: str) -> None:
        if tag in ('script', 'style', 'noscript') and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = data.strip()
        if text:
            self._chunks.append(text)

    def text(self) -> str:
        joined = ' '.join(self._chunks)
        joined = html.unescape(joined)
        joined = re.sub(r'[ \t]+', ' ', joined)
        joined = re.sub(r'\n{3,}', '\n\n', joined)
        return joined.strip()


def _html_to_text(content: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(content)
        parser.close()
    except Exception:  # pylint: disable=broad-except
        return re.sub(r'<[^>]+>', ' ', content)
    return parser.text()


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit].rstrip() + '\n...[truncated]', True


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update({'User-Agent': _USER_AGENT, 'Accept': '*/*'})
    return session


def fetch_url(arguments: dict[str, Any]) -> dict[str, Any]:
    """Fetch a public HTTP(S) page and return extracted text."""
    url = _validate_public_http_url(str(arguments.get('url') or ''))
    timeout = _fetch_timeout()
    max_bytes = _fetch_max_bytes()
    max_chars = _fetch_max_chars()

    with _session() as session:
        response = session.get(url, timeout=timeout, allow_redirects=True, stream=True)
        response.raise_for_status()
        final_url = response.url
        if final_url != url:
            _validate_public_http_url(final_url)

        content_type = (response.headers.get('Content-Type') or '').lower()
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_content(chunk_size=8192):
            if not chunk:
                continue
            size += len(chunk)
            if size > max_bytes:
                chunks.append(chunk[: max(0, max_bytes - (size - len(chunk)))])
                break
            chunks.append(chunk)
        raw = b''.join(chunks)
        truncated_bytes = size > max_bytes

    charset = 'utf-8'
    if 'charset=' in content_type:
        charset = content_type.split('charset=', 1)[1].split(';', 1)[0].strip() or charset
    try:
        body = raw.decode(charset, errors='replace')
    except LookupError:
        body = raw.decode('utf-8', errors='replace')

    if 'html' in content_type or body.lstrip().startswith('<'):
        text = _html_to_text(body)
    else:
        text = body

    text, truncated_chars = _truncate(text, max_chars)
    return {
        'url': final_url,
        'status_code': response.status_code,
        'content_type': content_type or None,
        'text': text,
        'truncated': truncated_bytes or truncated_chars,
    }


def _decode_ddg_redirect(href: str) -> str:
    parsed = urlparse(href)
    if parsed.netloc.endswith('duckduckgo.com') and parsed.path == '/l/':
        target = parse_qs(parsed.query).get('uddg', [''])[0]
        if target:
            return unquote(target)
    return href


def _parse_ddg_html_results(html_doc: str, limit: int) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for match in re.finditer(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        html_doc,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        href = html.unescape(_decode_ddg_redirect(match.group(1)))
        title = re.sub(r'<[^>]+>', '', match.group(2))
        title = html.unescape(re.sub(r'\s+', ' ', title)).strip()
        if not title or not href.startswith(('http://', 'https://')):
            continue
        results.append({'title': title, 'url': href})
        if len(results) >= limit:
            break

    if results:
        return results

    for match in re.finditer(
        r'<a[^>]+href="(https?://[^"]+)"[^>]*class="[^"]*result[^"]*"[^>]*>(.*?)</a>',
        html_doc,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        href = html.unescape(match.group(1))
        title = re.sub(r'<[^>]+>', '', match.group(2))
        title = html.unescape(re.sub(r'\s+', ' ', title)).strip()
        if not title:
            continue
        results.append({'title': title, 'url': href})
        if len(results) >= limit:
            break
    return results


def web_search(arguments: dict[str, Any]) -> dict[str, Any]:
    """Search the public web via DuckDuckGo HTML results."""
    query = str(arguments.get('query') or arguments.get('q') or '').strip()
    if not query:
        return {'error': 'query is required'}
    limit = _search_max_results()
    raw_limit = arguments.get('max_results')
    if raw_limit is not None:
        try:
            limit = max(1, min(int(raw_limit), _search_max_results()))
        except (TypeError, ValueError):
            pass

    with _session() as session:
        response = session.post(
            'https://html.duckduckgo.com/html/',
            data={'q': query, 'b': '', 'kl': ''},
            timeout=_fetch_timeout(),
            allow_redirects=True,
        )
        response.raise_for_status()

    results = _parse_ddg_html_results(response.text, limit)
    return {'query': query, 'results': results, 'count': len(results)}
