"""Configuration primitives: no variable prefixes or application defaults embedded."""
import io
import ipaddress
import re


class ConfigurationError(ValueError):
    pass


def port_number(value):
    value = str(value).strip()
    if not re.fullmatch(r'[0-9]{1,5}', value) or not 1 <= int(value) <= 65535:
        raise ConfigurationError('invalid_port')
    return str(int(value))


def host_name(value):
    value = str(value).strip()
    try:
        ipaddress.ip_address(value)
    except ValueError:
        if (len(value) > 253 or not value or re.fullmatch(r'[0-9.]+', value) or
                any(not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', part)
                    for part in value.rstrip('.').split('.'))):
            raise ConfigurationError('invalid_host')
    return value


def update_env(original, updates):
    """Preserve unrelated lines/comments; collapse duplicates of updated keys.

    Values must already be safe single-line dotenv literals (e.g. port/IP/Base64).
    Secret encoding/encryption, variable names and validation belong to the host.
    python-dotenv is loaded only when this function is called.
    """
    from dotenv.parser import parse_stream
    if any(not isinstance(k, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', k)
           or not isinstance(v, str) or not re.fullmatch(r'[A-Za-z0-9_./:=+@-]*', v)
           for k, v in updates.items()):
        raise ConfigurationError('unsafe_env_literal')
    output, written = [], set()
    for binding in parse_stream(io.StringIO(original)):
        if binding.error:
            raise ConfigurationError('invalid_env')
        if binding.key in updates:
            if binding.key not in written:
                output.append(binding.key + '=' + updates[binding.key] + '\n')
                written.add(binding.key)
        else:
            output.append(binding.original.string)
    text = ''.join(output)
    if text and not text.endswith('\n'):
        text += '\n'
    return text + ''.join(k + '=' + v + '\n' for k, v in updates.items() if k not in written)


def probe_bind(host, port, *, reserved_ports=()):
    """Probe a numeric local address without DNS or taking ownership of a listener.

    Returns available/unchecked; busy raises ConfigurationError. This is a
    point-in-time check, not a reservation or assurance a later bind will work.
    """
    import errno
    import os
    import socket
    port = int(port_number(port))
    if port in reserved_ports:
        raise ConfigurationError('port_busy')
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return 'port_unchecked'
    family = socket.AF_INET6 if address.version == 6 else socket.AF_INET
    try:
        with socket.socket(family, socket.SOCK_STREAM) as sock:
            if os.name == 'nt' and hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            sock.bind((str(address), port))
    except OSError as exc:
        if exc.errno == errno.EADDRNOTAVAIL:
            return 'port_unchecked'
        raise ConfigurationError('port_busy') from exc
    return 'port_available'
