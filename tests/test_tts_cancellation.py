from __future__ import annotations

import queue
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from ai_player.adapters.media.ffmpeg import ProcessCancelled
from ai_player.adapters.tts import tts_base, tts_vieneu
from ai_player.application.workflows.realtime import DubbingWorker
from ai_player.configuration import AppConfig


def test_cancel_vieneu_request_terminates_child_and_skips_fallback(monkeypatch, tmp_path) -> None:
    client = tts_vieneu.VieNeuServerClient(AppConfig())
    cancelled = threading.Event()
    waiting = threading.Event()
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    client._process = child
    client._output_queue = queue.Queue()
    monkeypatch.setattr(client, "_ensure_started", lambda: None)
    monkeypatch.setattr(client, "_write_payload", lambda _payload: waiting.set())
    monkeypatch.setattr(tts_vieneu, "_get_shared_vieneu_server", lambda _config: client)
    provider = tts_vieneu.VieNeuTTSProvider(AppConfig())
    monkeypatch.setattr(provider, "_should_use_subprocess", lambda _config: True)
    monkeypatch.setattr(provider, "_reset_server", lambda: pytest.fail("Cancellation must not trigger fallback"))
    provider.set_cancel_callback(cancelled.is_set)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(provider.synthesize, "hello", tmp_path / "out.wav")
            assert waiting.wait(2)
            cancelled.set()
            with pytest.raises(ProcessCancelled):
                future.result(timeout=2)
        assert child.poll() is not None
        assert client._process is None
        assert client._cancel_callback is None
        assert client._lock.acquire(blocking=False)
        client._lock.release()
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=2)
        child.stdin.close()
        child.stdout.close()


def test_cancel_while_waiting_for_shared_vieneu_does_not_stop_other_request(tmp_path) -> None:
    client = tts_vieneu.VieNeuServerClient(AppConfig())
    active_process = object()
    client._process = active_process
    cancelled = threading.Event()
    client._lock.acquire()
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                client.synthesize,
                text="hello",
                voice="Doan",
                output_path=tmp_path / "out.wav",
                temperature=0.6,
                max_chars=160,
                cancel_callback=cancelled.is_set,
            )
            cancelled.set()
            with pytest.raises(ProcessCancelled):
                future.result(timeout=1)
        assert client._process is active_process
        assert client._lock.locked()
    finally:
        client._lock.release()


def test_tts_cache_lock_wait_can_be_cancelled(monkeypatch, tmp_path) -> None:
    cache_path = tmp_path / "cache.wav"
    monkeypatch.setattr(tts_base, "_tts_cache_enabled", lambda: True)
    monkeypatch.setattr(tts_base, "_tts_cache_path", lambda *_args: cache_path)
    inner = tts_base.BaseTTSProvider()
    provider = tts_base.CachedTTSProvider(inner, AppConfig(), "vieneu")
    cancelled = threading.Event()
    provider.set_cancel_callback(cancelled.is_set)
    lock = tts_base._tts_cache_lock_for(cache_path)
    lock.acquire()
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(provider.synthesize, "hello", tmp_path / "out.wav")
            cancelled.set()
            with pytest.raises(ProcessCancelled):
                future.result(timeout=1)
        with pytest.raises(ProcessCancelled):
            inner._check_cancelled()
        assert not cache_path.exists()
    finally:
        lock.release()


def test_dubbing_stop_requests_audio_termination_without_waiting() -> None:
    terminated = []
    worker = SimpleNamespace(
        _stop_requested=False,
        _source_audio_cache_cancel=False,
        _active_audio_processes=[SimpleNamespace(poll=lambda: None, terminate=lambda: terminated.append(True))],
    )
    DubbingWorker.stop(worker)
    assert worker._stop_requested
    assert worker._source_audio_cache_cancel
    assert terminated == [True]
    assert DubbingWorker._launch_due_audio(worker, 0) is False
