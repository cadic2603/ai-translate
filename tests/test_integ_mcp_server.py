"""Integration test for the MCP server's translate_document tool.

End-to-end: enqueue a small text file via translate_document → poll
get_task_status until the in-process pipeline thread completes →
verify the entry's status flips to Done. The LLM is mocked; the
DB plumbing, background-pipeline thread, and task-id polling are
exercised for real so any wiring break (background thread leak,
status-not-flipped) is caught.
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest


@pytest.fixture()
def _isolated_data_dir(tmp_path, monkeypatch):
    """Redirect the app data dir so setup_translation_tasks clones into tmp."""
    data_dir = tmp_path / "appdata"
    data_dir.mkdir()
    monkeypatch.setattr(
        "src.utils.path_manager.get_app_data_dir", lambda: data_dir,
    )
    yield data_dir


class TestTranslateDocumentEndToEnd:
    """``translate_document`` → background pipeline → ``get_task_status`` flips Done.

    Pins the contract that translate_document is non-blocking (returns task
    IDs synchronously and spawns a daemon thread), the pipeline thread
    actually runs, and get_task_status polling reflects the Done flip
    once the worker finishes.  Without these guarantees the MCP surface
    would silently swallow errors or never advertise completion.
    """

    def test_pipeline_lands_status_done_within_deadline(
        self,
        tmp_path,
        _isolated_data_dir,  # noqa: ARG002
    ) -> None:
        """Real pipeline thread + real DB; LLM mocked."""
        src_file = tmp_path / "hello.txt"
        src_file.write_text("Hello world", encoding="utf-8")

        out_dir = tmp_path / "out"
        out_dir.mkdir()

        # Mocked LLM returns uppercased input; mirrors the per-batch contract.
        # Patch ``translate_text`` (the high-level entry) so dispatch to
        # provider-specific functions (which require API keys) is bypassed.
        def _fake_translate_text(texts, *_a, **_kw):  # noqa: ANN001
            return [t.upper() for t in texts]

        with (
            patch(
                "src.utils.config_manager.check_llm_setup", return_value=True,
            ),
            patch(
                "src.core.llm_engine.translate_text",
                side_effect=_fake_translate_text,
            ),
        ):
            from src.mcp_server import (  # noqa: PLC0415
                get_task_status,
                translate_document,
            )

            result = translate_document(
                file_paths=[str(src_file)],
                target_language="French",
                source_language="English (US)",
                output_directory=str(out_dir),
            )

            assert result["file_count"] == 1
            task_ids = result["task_ids"]
            assert len(task_ids) == 1

            # Poll up to ~10 s for the background thread to land "Done".
            deadline = time.monotonic() + 10.0
            entry: dict | None = None
            while time.monotonic() < deadline:
                statuses = get_task_status(task_ids=task_ids)
                entry = statuses[0]
                if entry and entry.get("status") == "Done":
                    break
                time.sleep(0.1)

            assert entry is not None
            assert entry.get("status") == "Done", (
                f"Background pipeline didn't complete in 10s — got {entry}"
            )

        # Output file should exist under the configured output directory
        # and contain the uppercased translation.
        produced = list(out_dir.iterdir())
        assert produced, "translate_document didn't write any output file"
        assert "HELLO WORLD" in produced[0].read_text(encoding="utf-8")
