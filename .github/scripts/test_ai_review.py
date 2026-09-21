import unittest
from base64 import b64encode
from unittest.mock import call, patch

import ai_review

FINDING = {
    "severity": "HIGH",
    "title": "Broken behavior",
    "path": "backend/example.py",
    "line": 12,
    "side": "RIGHT",
    "impact": "The request fails.",
    "fix": "Return the expected value.",
    "suggestion": "return expected",
}


class ExtractOutputTextTests(unittest.TestCase):
    def test_extracts_response_text(self) -> None:
        response = {
            "output": [
                {"content": [{"type": "output_text", "text": "  Review result  "}]}
            ]
        }

        self.assertEqual(ai_review.extract_output_text(response), "Review result")

    def test_rejects_response_without_text(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "did not contain output text"):
            ai_review.extract_output_text({"output": []})


class ExtractFindingsTests(unittest.TestCase):
    def test_extracts_structured_findings(self) -> None:
        response = {
            "output": [
                {
                    "content": [
                        {
                            "type": "output_text",
                            "text": '{"findings": [{"severity": "HIGH"}]}',
                        }
                    ]
                }
            ]
        }

        self.assertEqual(ai_review.extract_findings(response), [{"severity": "HIGH"}])


class ProjectContextTests(unittest.TestCase):
    @patch("ai_review.request_json")
    def test_loads_context_from_pull_request_commit(self, request_json) -> None:
        request_json.side_effect = [
            {
                "encoding": "base64",
                "content": b64encode(f"content for {path}".encode()).decode(),
            }
            for path in ai_review.PROJECT_CONTEXT_PATHS
        ]

        context = ai_review.get_project_context("owner/repo", "commit-sha", "token")

        for path in ai_review.PROJECT_CONTEXT_PATHS:
            self.assertIn(f"### {path}", context)
            self.assertIn(f"content for {path}", context)
        self.assertEqual(
            request_json.call_args_list,
            [
                call(
                    f"https://api.github.com/repos/owner/repo/contents/{path}"
                    "?ref=commit-sha",
                    token="token",
                )
                for path in ai_review.PROJECT_CONTEXT_PATHS
            ],
        )


class PublishCommentTests(unittest.TestCase):
    @patch("ai_review.request_json")
    def test_updates_existing_bot_comment(self, request_json) -> None:
        request_json.side_effect = [
            [
                {
                    "id": 42,
                    "body": ai_review.COMMENT_MARKER,
                    "user": {"login": "github-actions[bot]"},
                }
            ],
            {},
        ]

        ai_review.publish_comment("owner/repo", 7, "token", "new review")

        self.assertEqual(
            request_json.call_args_list,
            [
                call(
                    "https://api.github.com/repos/owner/repo/issues/7/comments"
                    "?per_page=100&page=1",
                    token="token",
                ),
                call(
                    "https://api.github.com/repos/owner/repo/issues/comments/42",
                    token="token",
                    method="PATCH",
                    payload={"body": "new review"},
                ),
            ],
        )

    @patch("ai_review.request_json")
    def test_creates_comment_when_none_exists(self, request_json) -> None:
        request_json.side_effect = [[], {}]

        ai_review.publish_comment("owner/repo", 7, "token", "new review")

        request_json.assert_has_calls(
            [
                call(
                    "https://api.github.com/repos/owner/repo/issues/7/comments",
                    token="token",
                    method="POST",
                    payload={"body": "new review"},
                )
            ]
        )


class CommitStatusTests(unittest.TestCase):
    @patch("ai_review.request_json")
    def test_sets_status_on_pull_request_commit(self, request_json) -> None:
        ai_review.set_commit_status(
            "owner/repo",
            "commit-sha",
            "token",
            state="success",
            description="AI review completed",
            target_url="https://github.example/review",
        )

        request_json.assert_called_once_with(
            "https://api.github.com/repos/owner/repo/statuses/commit-sha",
            token="token",
            method="POST",
            payload={
                "context": "AI Review",
                "description": "AI review completed",
                "state": "success",
                "target_url": "https://github.example/review",
            },
        )


class PublishFindingsTests(unittest.TestCase):
    @patch("ai_review.request_json")
    def test_creates_one_inline_comment_per_finding(self, request_json) -> None:
        request_json.side_effect = [[], {}]

        ai_review.publish_findings("owner/repo", 7, "commit-sha", "token", [FINDING])

        request_json.assert_has_calls(
            [
                call(
                    "https://api.github.com/repos/owner/repo/pulls/7/comments",
                    token="token",
                    method="POST",
                    payload={
                        "body": ai_review.format_finding(FINDING),
                        "commit_id": "commit-sha",
                        "line": 12,
                        "path": "backend/example.py",
                        "side": "RIGHT",
                    },
                )
            ]
        )

    @patch("ai_review.request_json")
    def test_updates_current_and_deletes_stale_findings(self, request_json) -> None:
        current_marker = ai_review.finding_marker(FINDING)
        request_json.side_effect = [
            [
                {
                    "id": 41,
                    "body": f"{current_marker}\nold body",
                    "user": {"login": "github-actions[bot]"},
                },
                {
                    "id": 42,
                    "body": "<!-- relaymaid-ai-finding:stale -->\nold body",
                    "user": {"login": "github-actions[bot]"},
                },
            ],
            {},
            None,
        ]

        ai_review.publish_findings("owner/repo", 7, "commit-sha", "token", [FINDING])

        request_json.assert_has_calls(
            [
                call(
                    "https://api.github.com/repos/owner/repo/pulls/comments/41",
                    token="token",
                    method="PATCH",
                    payload={"body": ai_review.format_finding(FINDING)},
                ),
                call(
                    "https://api.github.com/repos/owner/repo/pulls/comments/42",
                    token="token",
                    method="DELETE",
                ),
            ]
        )


class MainTests(unittest.TestCase):
    @patch.dict(
        "os.environ",
        {
            "EXPECTED_HEAD_SHA": "new-commit",
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_TOKEN": "token",
            "PR_NUMBER": "7",
        },
        clear=True,
    )
    @patch("ai_review.create_review")
    @patch(
        "ai_review.get_pull_request_diff",
        return_value=("diff", "old-commit", False, False),
    )
    def test_does_not_review_stale_successful_run(
        self, get_pull_request_diff, create_review
    ) -> None:
        ai_review.main()

        get_pull_request_diff.assert_called_once_with("owner/repo", 7, "token")
        create_review.assert_not_called()

    @patch.dict(
        "os.environ",
        {
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_TOKEN": "token",
            "PR_NUMBER": "7",
        },
        clear=True,
    )
    @patch("ai_review.create_review")
    @patch(
        "ai_review.get_pull_request_diff",
        return_value=("diff", "commit", False, True),
    )
    def test_does_not_review_draft(self, get_pull_request_diff, create_review) -> None:
        ai_review.main()

        get_pull_request_diff.assert_called_once_with("owner/repo", 7, "token")
        create_review.assert_not_called()


if __name__ == "__main__":
    unittest.main()
