"""C-22: una sola esecuzione per compito, lock in memoria (spec 04, D1)."""

from __future__ import annotations

from agente.task_lock import TaskLock


def test_first_acquire_succeeds_and_holds_the_task() -> None:
    lock = TaskLock()

    assert lock.acquire(7) is True
    assert lock.held(7) is True


def test_second_acquire_is_refused() -> None:
    lock = TaskLock()
    lock.acquire(7)

    assert lock.acquire(7) is False
    assert lock.held(7) is True


def test_release_frees_the_task() -> None:
    lock = TaskLock()
    lock.acquire(7)

    lock.release(7)

    assert lock.held(7) is False
    assert lock.acquire(7) is True


def test_release_is_idempotent() -> None:
    lock = TaskLock()

    lock.release(7)
    lock.release(7)

    assert lock.held(7) is False


def test_locks_are_per_task() -> None:
    lock = TaskLock()

    assert lock.acquire(1) is True
    assert lock.acquire(2) is True
    assert lock.held(1) and lock.held(2)

    lock.release(1)

    assert lock.held(1) is False
    assert lock.held(2) is True
