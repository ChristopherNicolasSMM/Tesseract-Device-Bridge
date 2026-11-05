"""Bounded read-only serial sessions with explicit ownership and idle expiry.

Reuse by injecting an opener/enumerator, or use the lazy pyserial defaults.
The host must provide authentication and its own operational interlocks.
No serial data is transmitted. Opening can still toggle USB control lines.
"""
import atexit
import re
import secrets
import threading
import time


class SerialError(ValueError):
    def __init__(self, message, *, code='serial_error'):
        self.code = code
        super().__init__(message)


def _ports():
    from serial.tools import list_ports
    return list_ports.comports()


def _open(**settings):
    from serial import Serial
    return Serial(**settings)


def validate_settings(port, baudrate=9600, bytesize=8, parity='N', stopbits=1):
    # Native serial paths only: never accept RFC2217/socket URLs or arbitrary files.
    if not isinstance(port, str) or not re.fullmatch(
            r'(?:COM[1-9][0-9]{0,3}|/dev/tty(?:USB|ACM|AMA|S|THS)[0-9]{1,4}|'
            r'/dev/(?:tty|cu)\.[A-Za-z0-9_-]{1,128}|/dev/serial/by-id/[A-Za-z0-9_.:+-]{1,200})', port):
        raise SerialError('Porta serial nativa inválida (COM, /dev/tty ou /dev/serial/by-id).', code='invalid_port')
    if type(baudrate) is not int or not 300 <= baudrate <= 2000000:
        raise SerialError('Baud rate deve ser inteiro entre 300 e 2000000.', code='invalid_baudrate')
    if type(bytesize) is not int or bytesize not in (5, 6, 7, 8):
        raise SerialError('Bits de dados devem ser 5, 6, 7 ou 8.', code='invalid_bytesize')
    if not isinstance(parity, str) or parity not in ('N', 'E', 'O', 'M', 'S'):
        raise SerialError('Paridade inválida.', code='invalid_parity')
    if type(stopbits) not in (int, float) or stopbits not in (1, 1.5, 2):
        raise SerialError('Bits de parada inválidos.', code='invalid_stopbits')
    return dict(port=port, baudrate=baudrate, bytesize=bytesize, parity=parity, stopbits=stopbits)


class SerialMonitor:
    """One active connection per host process, owned by an opaque browser identity.

    Idle closure runs on a daemon timer, including when the browser disappears.
    Call close_all() on host shutdown. A host with multiple workers must supply
    a shared broker; an in-memory monitor is intentionally single-process.
    """
    def __init__(self, *, opener=None, enumerator=None, idle_seconds=30):
        self.opener = opener or _open
        self.enumerator = enumerator or _ports
        self.idle_seconds = idle_seconds
        self._lock = threading.RLock()
        self._session = None
        self._timer = None
        atexit.register(self.close_all)

    def ports(self):
        try:
            rows = sorted(self.enumerator(), key=lambda p: p.device)
            return dict(available=True, ports=[dict(device=p.device, description=p.description,
                hwid=getattr(p, 'hwid', None)) for p in rows],
                message='Portas do servidor, independentes do cadastro. Abrir pode reiniciar o equipamento.')
        except (ImportError, OSError) as exc:
            return dict(available=False, ports=[], message='Não foi possível listar portas: ' + str(exc))

    def _close(self):
        if self._timer:
            self._timer.cancel()
            self._timer = None
        active, self._session = self._session, None
        if active:
            try:
                active['connection'].close()
            except Exception:
                pass  # Release registry even after a USB device disappears.

    def _expire(self, identifier):
        with self._lock:
            if self._session and self._session['id'] == identifier:
                remaining = self.idle_seconds - (time.monotonic() - self._session['last_read'])
                if remaining > 0:
                    self._schedule(identifier, remaining)
                else:
                    self._close()

    def _schedule(self, identifier, seconds):
        if self._timer:
            self._timer.cancel()
        self._timer = threading.Timer(seconds, self._expire, args=(identifier,))
        self._timer.daemon = True
        self._timer.start()

    def open(self, owner, **settings):
        settings = validate_settings(**settings)
        with self._lock:
            if self._session:
                raise SerialError('Monitor ocupado. Encerre a conexão anterior ou aguarde expiração.', code='monitor_busy')
            connection = None
            try:
                connection = self.opener(port=None, baudrate=settings['baudrate'],
                    bytesize=settings['bytesize'], parity=settings['parity'], stopbits=settings['stopbits'],
                    timeout=0.2, write_timeout=0.2, xonxoff=False, rtscts=False, dsrdtr=False)
                connection.dtr = False
                connection.rts = False
                connection.port = settings['port']
                connection.open()
            except Exception as exc:
                if connection is not None:
                    try:
                        connection.close()
                    except Exception:
                        pass
                raise SerialError('Não foi possível abrir a porta: ' + str(exc), code='open_failed') from exc
            identifier = secrets.token_urlsafe(24)
            self._session = dict(id=identifier, owner=owner, connection=connection,
                                 settings=settings, last_read=time.monotonic())
            self._schedule(identifier, self.idle_seconds)
            return dict(session=identifier, idle_seconds=self.idle_seconds,
                        mode='read_only', **settings)

    def _owned(self, identifier, owner):
        active = self._session
        if (not active or active['id'] != identifier or active['owner'] != owner):
            raise SerialError('Sessão serial inexistente, expirada ou de outro navegador.', code='session_not_found')
        if time.monotonic() - active['last_read'] >= self.idle_seconds:
            self._close()
            raise SerialError('Sessão serial expirada por inatividade.', code='session_expired')
        return active

    def read(self, identifier, owner, limit=1024):
        if type(limit) is not int or not 1 <= limit <= 4096:
            raise SerialError('Limite de leitura deve estar entre 1 e 4096 bytes.', code='invalid_limit')
        with self._lock:
            active = self._owned(identifier, owner)
            try:
                chunk = active['connection'].read(limit)
            except Exception as exc:
                self._close()
                raise SerialError('Falha na leitura; conexão encerrada: ' + str(exc), code='read_failed') from exc
            active['last_read'] = time.monotonic()
            return dict(port=active['settings']['port'], baudrate=active['settings']['baudrate'],
                        text=chunk.decode('utf-8', errors='replace'), hex=chunk.hex(' '),
                        bytes_read=len(chunk), mode='read_only')

    def close(self, identifier, owner):
        with self._lock:
            self._owned(identifier, owner)
            self._close()

    def close_owner(self, owner):
        with self._lock:
            if self._session and self._session['owner'] == owner:
                self._close()

    def close_all(self):
        with self._lock:
            self._close()

    def test(self, owner, **settings):
        opened = self.open(owner, **settings)
        self.close(opened['session'], owner)
        return dict(port=opened['port'], status='opened_and_closed', mode='read_only',
                    message='Abertura concluída; isto não valida protocolo nem identidade do equipamento.')
