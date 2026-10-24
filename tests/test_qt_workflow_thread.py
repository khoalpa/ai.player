from __future__ import annotations

import time

import pytest
from PySide6.QtCore import Signal
from PySide6.QtTest import QTest

from ai_player.adapters.qt.workflow_thread import WorkflowThread
from ai_player.application.events import Event, Workflow
from ai_player.application.jobs import JobManager, JobStatus

pytestmark = pytest.mark.slow


class SampleWorkflow(Workflow):
    ready = Event(str)
    failed = Event(str)

    def __init__(self, text: str, pause: float = 0.0, parent=None):
        super().__init__(parent)
        self.text = text
        self.pause = pause

    def run(self):
        if self.cancellation.wait(self.pause):
            return
        self.ready.emit(self.text)


class SampleThread(WorkflowThread):
    workflow_type = SampleWorkflow
    event_names = ("ready", "failed")
    ready = Signal(str)
    failed = Signal(str)


def settle(worker, qapp):
    deadline = time.monotonic() + 5
    while worker.isRunning() and time.monotonic() < deadline:
        QTest.qWait(5)
    assert worker.wait(1000)
    qapp.processEvents()


def test_thread_delivers_result_before_recording_completion(qapp):
    manager = JobManager()
    worker = SampleThread("ready", manager=manager)
    received = []
    worker.ready.connect(received.append)
    worker.start()
    settle(worker, qapp)
    assert received == ["ready"]
    assert manager.snapshots()[0].status == JobStatus.SUCCEEDED


def test_queued_events_from_replaced_task_are_rejected(qapp):
    manager = JobManager()
    old = SampleThread("old", manager=manager)
    received = []
    old.ready.connect(received.append)
    old.start()
    assert old.wait(1000)  # Leave the emitted event queued on the UI thread.
    current = SampleThread("current", manager=manager)
    current.ready.connect(received.append)
    current.start()
    settle(current, qapp)
    assert received == ["current"]
    assert manager.snapshots()[0].status == JobStatus.CANCELLED


def test_cooperative_cancel_stops_thread_without_emitting_result(qapp):
    manager = JobManager()
    worker = SampleThread("unwanted", pause=10, manager=manager)
    received = []
    worker.ready.connect(received.append)
    worker.start()
    worker.stop()
    settle(worker, qapp)
    assert not received
    assert manager.snapshots()[0].status == JobStatus.CANCELLED
