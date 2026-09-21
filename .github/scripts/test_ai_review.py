import unittest
from unittest.mock import call, patch

import ai_review


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
