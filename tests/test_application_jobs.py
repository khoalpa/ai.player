from __future__ import annotations

from pathlib import Path

import pytest

from ai_player.adapters.storage.cache_store import ArtifactCache
from ai_player.application.jobs import JobCancelled, JobManager, JobStatus
from ai_player.application.speech import SpeechService


def test_replacement_cancels_old_job_and_rejects_late_results():
    manager = JobManager()
    old = manager.create("source")
    manager.start(old.id)
    new = manager.create("source")
    assert old.token.cancelled
    assert not manager.update(old.id, detail="late result")
    assert manager.start(new.id)
    assert manager.update(new.id, progress=25)
    manager.finish(old.id)
    manager.finish(new.id)
    assert [job.status for job in manager.snapshots()] == [JobStatus.CANCELLED, JobStatus.SUCCEEDED]


def test_cancel_is_terminal_only_after_worker_finishes():
    manager = JobManager()
    job = manager.create("export")
    manager.start(job.id)
    manager.cancel_all()
    assert manager.snapshots()[0].status == JobStatus.CANCELLING
    with pytest.raises(JobCancelled):
        job.token.check()
    manager.finish(job.id, error="cancelled by provider")
    assert manager.snapshots()[0].status == JobStatus.CANCELLED
    assert not manager.start(job.id)
    assert not manager.finish(job.id)


def test_history_bound_does_not_remove_active_jobs():
    manager = JobManager(history_limit=2)
    active = manager.create("active")
    for index in range(12):
        job = manager.create(str(index))
        manager.finish(job.id)
    assert len(manager.snapshots()) == 3
    assert manager.accepts_result(active.id)


@pytest.mark.parametrize("cancel", [False, True])
def test_speech_does_not_publish_partial_or_cancelled_output(tmp_path, cancel):
    output = tmp_path / "voice.wav"
    output.write_bytes(b"previous result")

    class Provider:
        def callback(self):
            return False

        def set_cancel_callback(self, callback):
            self.callback = callback

        def synthesize(self, text, destination, voice=None):
            destination.write_bytes(b"partial")
            if not cancel:
                raise RuntimeError("provider failed")

    provider = Provider()
    service = SpeechService(provider)
    calls = []
    service.set_cancel_callback(lambda: bool(calls) if cancel else False)
    original = provider.synthesize

    def synthesize(*args, **kwargs):
        calls.append(True)
        original(*args, **kwargs)

    provider.synthesize = synthesize
    with pytest.raises((RuntimeError, JobCancelled)):
        service.synthesize("hello", output)
    assert output.read_bytes() == b"previous result"
    assert list(tmp_path.iterdir()) == [output]


def test_cache_cleanup_preserves_leased_entries(tmp_path):
    cache = ArtifactCache(tmp_path)
    active = tmp_path / "active.wav"
    active.write_bytes(b"active")
    unused = tmp_path / "unused.wav"
    unused.write_bytes(b"unused")
    with cache.lease(active):
        assert cache.prune(max_bytes=0) == 1
        assert active.is_file()
    assert cache.prune(max_bytes=0) == 1
    with pytest.raises(ValueError):
        with cache.lease(Path(tmp_path).parent / "outside.wav"):
            pass
