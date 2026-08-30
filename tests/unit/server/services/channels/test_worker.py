from __future__ import annotations


def test_worker_does_not_import_fastapi_lifespan():
    import inspect

    import src.server.services.channels.worker as worker

    assert "src.server.app.setup" not in inspect.getsource(worker)
    assert "max_text_length=config.max_ilink_text_length" in inspect.getsource(worker)
    assert callable(worker.run_worker)
