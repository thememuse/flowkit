"""Tests for manual-only regenerate policy (no bulk regen overwrite)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from agent.api import requests as requests_api
from agent.api import workflows as workflows_api
from agent.models.request import RequestCreate


def _scene_request(req_type: str, scene_id: str) -> RequestCreate:
    return RequestCreate(
        type=req_type,  # type: ignore[arg-type]
        project_id="project-001",
        video_id="video-001",
        scene_id=scene_id,
        orientation="VERTICAL",
    )


class TestBatchRegenGuard:
    @pytest.mark.asyncio
    async def test_rejects_bulk_regenerate_video(self):
        body = requests_api.BatchRequestCreate(
            requests=[
                _scene_request("REGENERATE_VIDEO", "scene-001"),
                _scene_request("REGENERATE_VIDEO", "scene-002"),
            ]
        )
        with pytest.raises(HTTPException) as exc:
            await requests_api.create_batch(body)
        assert exc.value.status_code == 400
        assert "tạo lại hàng loạt" in str(exc.value.detail)

    @pytest.mark.asyncio
    async def test_rejects_mixed_batch_with_regenerate(self):
        body = requests_api.BatchRequestCreate(
            requests=[
                _scene_request("REGENERATE_IMAGE", "scene-001"),
                _scene_request("GENERATE_VIDEO", "scene-001"),
            ]
        )
        with pytest.raises(HTTPException) as exc:
            await requests_api.create_batch(body)
        assert exc.value.status_code == 400
        assert "tạo lại hàng loạt" in str(exc.value.detail)

    @pytest.mark.asyncio
    async def test_allows_single_scene_regenerate(self, monkeypatch):
        async def _noop_validate(data):
            return data

        async def _no_cooldown(_project_id):
            return None

        async def _empty_list_requests(*args, **kwargs):
            return []

        async def _noop_update_video(*args, **kwargs):
            return None

        created_rows: list[dict] = []

        async def _create_request(**kwargs):
            row = {
                "id": "req-001",
                "project_id": kwargs.get("project_id"),
                "video_id": kwargs.get("video_id"),
                "scene_id": kwargs.get("scene_id"),
                "character_id": kwargs.get("character_id"),
                "type": kwargs.get("req_type"),
                "orientation": kwargs.get("orientation"),
                "status": kwargs.get("status", "PENDING"),
                "request_id": None,
                "media_id": None,
                "output_url": None,
                "error_message": kwargs.get("error_message"),
                "retry_count": 0,
                "next_retry_at": kwargs.get("next_retry_at"),
                "source_media_id": kwargs.get("source_media_id"),
                "created_at": None,
                "updated_at": None,
            }
            created_rows.append(row)
            return row

        monkeypatch.setattr(requests_api, "_validate_request_scope", _noop_validate)
        monkeypatch.setattr(
            requests_api, "_project_traffic_cooldown_until", _no_cooldown
        )
        monkeypatch.setattr(requests_api.crud, "list_requests", _empty_list_requests)
        monkeypatch.setattr(requests_api.crud, "update_video", _noop_update_video)
        monkeypatch.setattr(requests_api.crud, "create_request", _create_request)

        body = requests_api.BatchRequestCreate(
            requests=[_scene_request("REGENERATE_VIDEO", "scene-001")]
        )
        rows = await requests_api.create_batch(body)
        assert len(rows) == 1
        assert rows[0]["type"] == "REGENERATE_VIDEO"
        assert len(created_rows) == 1


class TestSmartContinueReviewManual:
    @pytest.mark.asyncio
    async def test_review_fail_returns_manual_followup_without_regen_enqueue(
        self, monkeypatch
    ):
        project_id = "project-001"
        video_id = "video-001"
        scene_id = "scene-001"

        scene_row = {
            "id": scene_id,
            "display_order": 0,
            "video_prompt": "Original prompt",
            "narrator_text": None,
            "vertical_image_media_id": "mid-001",
            "vertical_video_status": "COMPLETED",
            "vertical_upscale_status": "PENDING",
            "vertical_video_media_id": "vid-mid-001",
        }

        monkeypatch.setattr(
            workflows_api._repo,
            "get_video",
            AsyncMock(
                return_value={
                    "id": video_id,
                    "project_id": project_id,
                    "orientation": "VERTICAL",
                }
            ),
        )
        monkeypatch.setattr(
            workflows_api._repo,
            "get_project",
            AsyncMock(
                return_value={
                    "id": project_id,
                    "name": "Project",
                    "orientation": "VERTICAL",
                }
            ),
        )
        monkeypatch.setattr(
            workflows_api._repo, "list_scenes", AsyncMock(return_value=[scene_row])
        )
        monkeypatch.setattr(
            workflows_api._repo,
            "get_project_characters",
            AsyncMock(return_value=[]),
        )
        update_scene_mock = AsyncMock(return_value=None)
        monkeypatch.setattr(workflows_api._repo, "update", update_scene_mock)
        monkeypatch.setattr(workflows_api.crud, "update_video", AsyncMock(return_value=None))

        enqueue_mock = AsyncMock(return_value=True)
        monkeypatch.setattr(workflows_api, "_enqueue_request_if_needed", enqueue_mock)

        review_result = SimpleNamespace(
            overall_score=6.1,
            scene_reviews=[
                SimpleNamespace(
                    scene_id=scene_id,
                    overall_score=3.9,
                    has_critical_errors=True,
                    fix_guide="Tone down violent details and emphasize aftermath.",
                )
            ],
        )
        monkeypatch.setattr(
            workflows_api, "review_video", AsyncMock(return_value=review_result)
        )

        body = workflows_api.SmartContinueRequest(
            project_id=project_id,
            orientation="VERTICAL",
            include_upscale=True,
            review_before_upscale=True,
            review_threshold=7.5,
            max_review_regens=12,
            low_score_regen_image_threshold=4.0,
        )
        res = await workflows_api.smart_continue(video_id, body)

        assert res.action == "review_manual"
        assert res.queued_requests == 0
        assert res.requested_types == []
        assert res.review is not None
        assert res.review.get("auto_queue_disabled") is True
        manual_items = res.review.get("manual_regen_scenes", [])
        assert len(manual_items) == 1
        assert manual_items[0]["scene_id"] == scene_id
        assert manual_items[0]["suggested_request_type"] == "REGENERATE_IMAGE"
        assert enqueue_mock.await_count == 0
        assert update_scene_mock.await_count == 1
