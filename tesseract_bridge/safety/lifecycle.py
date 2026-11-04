"""Process boundaries for catchable shutdowns and uncaught worker exceptions."""
import signal
import threading
from contextlib import contextmanager


@contextmanager
def safety_lifecycle(runtime):
    previous_hook = threading.excepthook
    previous_signals = {}
    def worker_failed(args):
        runtime.trip(f"Falha na thread {args.thread.name}: {args.exc_value}")
        previous_hook(args)
    def terminate(signum, frame):
        raise SystemExit(128 + signum)
    threading.excepthook = worker_failed
    if threading.current_thread() is threading.main_thread():
        for signum in (signal.SIGTERM, signal.SIGINT):
            previous_signals[signum] = signal.getsignal(signum)
            signal.signal(signum, terminate)
    try:
        yield
    except BaseException as exc:
        runtime.trip(f"Encerramento por erro/sinal: {exc}")
        raise
    finally:
        runtime.trip("Encerramento do serviço")
        runtime.shutdown()
        threading.excepthook = previous_hook
        for signum, handler in previous_signals.items():
            signal.signal(signum, handler)
