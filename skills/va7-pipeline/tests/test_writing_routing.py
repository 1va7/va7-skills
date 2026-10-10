"""Behavioral regressions for artifact intent and version-specific continuation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SHARED = ROOT / "va7-interview" / "scripts"
sys.path.insert(0, str(SHARED))
from validate_content_brief import validate_data
from writing_intent import decide_writing_request

GATE = ROOT / "va7-script" / "scripts" / "pre_draft_gate.py"
ROUTER = ROOT / "va7-pipeline" / "scripts" / "route_content_task.py"
VALIDATOR = SHARED / "validate_content_brief.py"


def brief() -> dict:
    return {
        "idea": "skills version management",
        "library_status": "existing_ready",
        "user_position": "track changes before sharing versions",
        "audience": "teams using agents",
        "viewer_payoff": "recognize unreviewed changes",
        "key_tension": "local fixes can cause regressions",
        "mechanism": "capture, review, commit",
        "selected_direction": {"name": "version management", "thesis": "review changes", "why_va7_specific": "first-hand implementation"},
        "personal_evidence": [{"detail": "a user-provided customer case"}],
        "non_goals": ["all of SkillOps"],
        "claims_to_avoid": ["automatic quality improvement"],
        "confirmed_by_user": True,
    }


def state(stage: str = "full_draft", version: str = "v2") -> dict:
    return {
        "stage": stage,
        "outline_version": version,
        "outline_confirmation": {"outline_version": "v2", "source": "session#31", "quote": "这个大纲没问题"},
        "full_draft_authorization": {"outline_version": "v2", "source": "session#33", "quote": "按这个大纲写完整稿"},
        "draft_source": {"source": "session#34", "quote": "为什么 Skill 会越改越差？"},
    }


class IntentTests(unittest.TestCase):
    def check(self, text: str, decision: str, **kwargs) -> dict:
        result = decide_writing_request(text, **kwargs)
        self.assertEqual(result["decision"], decision, (text, result))
        self.assertEqual(result["may_write_full_draft"], decision == "ready_to_draft")
        return result

    def test_outline_limits_override_every_prior_permission(self):
        for text in [
            "不要直接写完整口播稿，先给我 bullet points 大纲。",
            "只给我大纲，不要写全文。",
            "先写大纲，再写完整稿。",
            "给我一个可以检查的提纲。",
            "不用采访，只给 bullet points。",
            "别写全文，给大纲",
            "先给我大纲，如果确认了再写完整稿",
        ]:
            with self.subTest(text=text):
                self.check(text, "ready_to_outline", brief_ready=True, writing_state=state(), user_confirmed_skip=True)

    def test_bare_full_prohibition_does_not_turn_into_permission(self):
        self.check("不要直接写完整口播稿。", "needs_context", brief_ready=True, writing_state=state(), user_confirmed_skip=True)

    def test_current_full_prohibition_blocks_all_old_authorization(self):
        for text in ["先不写完整稿，继续", "先别写正文，继续", "不要写口播稿，继续"]:
            with self.subTest(text=text):
                self.check(text, "needs_context", brief_ready=True, writing_state=state())
                self.check(text, "needs_context", brief_ready=True)

    def test_current_confirmation_needs_no_json_file(self):
        for text in ["大纲已经确认，可以按这个来写完整稿。", "已确认大纲，基于这个 brief 写完整稿", "这个提纲没问题，请写全文。"]:
            with self.subTest(text=text):
                result = self.check(text, "ready_to_draft")
                self.assertEqual(result["authorization"]["source"], "current_request")

    def test_outline_approval_alone_does_not_authorize_full_prose(self):
        self.check("这个大纲已经确认。", "needs_context")

    def test_direction_confirmation_and_old_brief_only_support_outline(self):
        self.check("已经确认方向，继续。", "ready_to_outline", brief_ready=True)
        self.check("继续", "ready_to_outline", brief_ready=True)
        self.check("基于这份 brief 继续", "ready_to_outline", brief_ready=True)

    def test_explicit_full_draft_branch_is_preserved(self):
        direct = self.check("不用写大纲，直接写完整稿。", "ready_to_draft")
        self.assertIsNone(direct["outline_confirmation_source"])
        self.check("直接写口播稿", "ready_to_draft")
        self.check("请写完整稿", "ready_to_draft", brief_ready=True)
        self.check("先别写大纲，直接写完整稿", "ready_to_draft")
        self.check("直接写一版", "ready_to_draft")
        self.check("不用采访，直接写一版口播稿", "ready_to_draft")

    def test_unresolved_current_outline_blocks_stale_permission(self):
        self.check("新版大纲还没确认，继续写完整稿", "needs_context", brief_ready=True, writing_state=state())
        for text in ["新版大纲还没确认，继续", "大纲未确认，继续", "未确认的大纲，继续"]:
            with self.subTest(text=text):
                self.check(text, "needs_context", brief_ready=True, writing_state=state())

    def test_expanding_an_outline_is_full_drafting_not_revision(self):
        for text in ["大纲已确认，请扩写成完整稿", "把已确认的大纲扩写成完整稿", "把已确认大纲扩写成完整稿"]:
            with self.subTest(text=text):
                self.check(text, "ready_to_draft")
                self.check(text, "ready_to_draft", brief_ready=True, writing_state=state())

    def test_continue_requires_same_outline_version(self):
        self.check("继续", "ready_to_draft", brief_ready=True, writing_state=state())
        result = self.check("继续", "needs_context", brief_ready=True, writing_state=state(version="v3"))
        self.assertTrue(result["warnings"])
        without_draft_permission = state()
        del without_draft_permission["full_draft_authorization"]
        self.check("继续", "needs_context", brief_ready=True, writing_state=without_draft_permission)

    def test_continue_outline_and_revision_resume_the_actual_stage(self):
        self.check("继续", "ready_to_outline", writing_state=state(stage="outline"))
        self.check("继续", "ready_to_revise", writing_state=state(stage="revise"))
        self.check("继续", "needs_context")

    def test_quoted_old_permission_is_not_a_current_instruction(self):
        for text in [
            "之前你说过“直接写完整稿”。这次只给大纲。",
            '参考句子："直接写完整稿"。只给我大纲。',
            "> 直接写完整稿\n先给我提纲。",
            "```text\n直接写完整稿\n```\n只给我大纲",
        ]:
            with self.subTest(text=text):
                self.check(text, "ready_to_outline")
        self.check("“直接写完整稿”", "needs_context")

    def test_ambiguous_or_conditional_requests_need_context(self):
        for text in [
            "如果大纲确认，再写完整稿。",
            "等大纲通过后再写全文。",
            "为什么你直接写完整稿？",
            "不是不要大纲，完整稿也不是不写。",
            "不是只给我大纲",
            "如果大纲确认再给我大纲",
        ]:
            with self.subTest(text=text):
                self.check(text, "needs_context", brief_ready=True)

    def test_raw_topic_and_revision_are_different_routes(self):
        self.check("我有个灵感，主题是 AI 转型", "route_to_interview")
        self.check("围绕 AI 转型写一篇口播稿", "route_to_interview")
        self.check("我有个灵感，先不用采访", "ready_to_outline", user_confirmed_skip=True)
        self.check("不用采访，围绕 AI 转型写一篇口播稿", "ready_to_outline")
        self.check("把我这版稿子清洗一下，不增加观点", "ready_to_revise")
        self.check("帮我改稿", "ready_to_revise")
        self.check("扩写", "needs_context")

    def test_invalid_state_and_incomplete_brief_recover_context(self):
        self.check("继续", "needs_context", has_brief=True, writing_state="bad")
        self.check("继续", "needs_context", has_brief=True)
        self.check("请写完整稿", "needs_context")


class CLITests(unittest.TestCase):
    def run_cli(self, script: Path, *args: str) -> tuple[int, dict]:
        result = subprocess.run([sys.executable, str(script), *args], text=True, capture_output=True, env=os.environ | {"PYTHONDONTWRITEBYTECODE": "1"}, timeout=10)
        self.assertIn(result.returncode, [0, 1], result.stderr)
        return result.returncode, json.loads(result.stdout)

    def test_gate_uses_staged_validator_and_state(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "brief.json"
            data = brief() | {"writing_state": state()}
            path.write_text(json.dumps(data), encoding="utf-8")
            code, result = self.run_cli(GATE, "--input", "只给大纲，不要写全文", "--brief", str(path), "--user-confirmed-skip")
            self.assertEqual((code, result["decision"]), (0, "ready_to_outline"))
            self.assertTrue(result["validator_report"]["ok"])
            code, result = self.run_cli(GATE, "--input", "继续", "--brief", str(path))
            self.assertEqual((code, result["decision"]), (0, "ready_to_draft"))
            data["writing_state"]["outline_version"] = "v3"
            path.write_text(json.dumps(data), encoding="utf-8")
            code, result = self.run_cli(GATE, "--input", "继续", "--brief", str(path))
            self.assertEqual((code, result["decision"]), (1, "needs_context"))

    def test_record_and_skip_flags_are_not_full_draft_authorization(self):
        code, result = self.run_cli(GATE, "--feishu-record", "rec-test", "--user-confirmed-skip")
        self.assertEqual((code, result["decision"]), (1, "needs_context"))
        self.assertFalse(result["may_write_full_draft"])

    def test_missing_and_non_object_brief_return_structured_errors(self):
        code, result = self.run_cli(GATE, "--input", "继续", "--brief", "/tmp/no-such-writing-brief-fixture.json")
        self.assertEqual((code, result["decision"]), (1, "needs_context"))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "brief.json"
            path.write_text("[]", encoding="utf-8")
            code, result = self.run_cli(VALIDATOR, "--brief", str(path))
            self.assertEqual(code, 1)
            self.assertIn("JSON object", result["errors"][0])

    def test_router_writing_and_media_regressions(self):
        cases = [
            ("只给我 bullet points 大纲", "outline_stage", "va7-script"),
            ("继续写这篇口播视频的大纲", "outline_stage", "va7-script"),
            ("直接写一版", "draft_stage", "va7-script"),
            ("现在只写大纲，先不要做封面和发布物料", "outline_stage", "va7-script"),
            ("给我这条口播视频的大纲，先不做封面", "outline_stage", "va7-script"),
            ("直接写完整稿，封面后面再做", "draft_stage", "va7-script"),
            ("已确认大纲，基于这个 brief 写完整稿", "draft_stage", "va7-script"),
            ("把我这版稿子清洗一下", "revision_stage", "va7-script"),
            ("我有个灵感，选题是AI转型", "new_raw_topic", "va7-interview"),
            ("我还不清楚下一步做什么", "needs_context", "va7-pipeline"),
            ("继续做封面图", "media_stage", "va7-video-cover-maker"),
            ("剪视频，加字幕", "media_stage", "va7-monologue-video-editor"),
            ("继续准备发布物料", "publish_stage", "va7-publish"),
            ("把这个稿子转成公众号文章", "wechat_stage", "wechat-converter"),
            ("帮我复盘这次写作", "review_stage", "agent-writing-rl-dataset"),
            ("把这个素材加到灵感库", "ingestion_stage", "va7-library"),
        ]
        for text, stage, skill in cases:
            with self.subTest(text=text):
                code, result = self.run_cli(ROUTER, "--input", text, "--no-base-search")
                self.assertEqual(code, 0)
                self.assertEqual((result["stage"], result["recommended_skill"]), (stage, skill))

    def test_explicit_outline_is_not_a_video_editing_request(self):
        _, result = self.run_cli(ROUTER, "--input", "给我这条口播视频的大纲", "--path", "/tmp/example.mov", "--no-base-search")
        self.assertEqual(result["stage"], "outline_stage")

    def test_router_restores_persisted_stage(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "brief.json"
            path.write_text(json.dumps(brief() | {"writing_state": state()}), encoding="utf-8")
            _, result = self.run_cli(ROUTER, "--input", "继续", "--brief", str(path), "--no-base-search")
            self.assertEqual(result["stage"], "draft_stage")

    def test_legacy_brief_does_not_hijack_media_or_publish_operations(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "brief.json"
            path.write_text(json.dumps(brief()), encoding="utf-8")
            for text, stage in [("剪视频，加字幕", "media_stage"), ("继续做封面图", "media_stage"), ("继续准备发布物料", "publish_stage")]:
                with self.subTest(text=text):
                    _, result = self.run_cli(ROUTER, "--input", text, "--brief", str(path), "--no-base-search")
                    self.assertEqual(result["stage"], stage)


class StateValidationTests(unittest.TestCase):
    def test_legacy_brief_confirms_direction_only(self):
        result = validate_data(brief())
        self.assertTrue(result["ok"])
        self.assertEqual(result["scope"], "content_direction_only")

    def test_confirmation_provenance_and_version_are_required(self):
        data = brief() | {"writing_state": state()}
        self.assertTrue(validate_data(data)["ok"])
        del data["writing_state"]["outline_confirmation"]["source"]
        self.assertFalse(validate_data(data)["ok"])

    def test_stale_confirmation_is_visible_not_a_schema_crash(self):
        result = validate_data(brief() | {"writing_state": state(version="v3")})
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["warnings"]), 2)


if __name__ == "__main__":
    unittest.main()
