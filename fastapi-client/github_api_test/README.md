## 테스트 케이스 목록

`github_pr_comment.http` 파일에 포함된 테스트 케이스는 다음과 같습니다.

> **참고:** 전체 Pull Requests API 문서는 [여기](https://docs.github.com/en/rest/pulls?apiVersion=2022-11-28)에서 확인하실 수 있습니다.

| 기능 | API Endpoint | GitHub 문서 | 결과 링크 |
| --- | --- | --- | --- |
| PR 일반 코멘트 목록 조회 | `GET /repos/{owner}/{repo}/issues/{pull_number}/comments` | [바로가기](https://docs.github.com/en/rest/issues/comments#list-issue-comments) | [바로가기](https://github.com/sjKang01401/webhook-test/pull/1) |
| PR에 일반 코멘트 작성 | `POST /repos/{owner}/{repo}/issues/{pull_number}/comments` | [바로가기](https://docs.github.com/ko/rest/issues/comments?apiVersion=2022-11-28#create-an-issue-comment) | [바로가기](https://github.com/sjKang01401/webhook-test/pull/1) |
| PR 리뷰 코멘트 목록 조회 | `GET /repos/{owner}/{repo}/pulls/{pull_number}/comments` | [바로가기](https://docs.github.com/en/rest/pulls/comments#list-review-comments-on-a-pull-request) | [바로가기](https://github.com/sjKang01401/webhook-test/pull/1/files) |
| PR에 리뷰 코멘트 작성 | `POST /repos/{owner}/{repo}/pulls/{pull_number}/comments` | [바로가기](https://docs.github.com/en/rest/pulls/comments?apiVersion=2022-11-28#create-a-review-comment-for-a-pull-request) | [바로가기](https://github.com/sjKang01401/webhook-test/pull/1/files) |