"""GitLab REST API client for code search and file retrieval."""

import logging
import time
from dataclasses import dataclass
from urllib.parse import quote

import httpx

from neoflow.config import GitLabConfig

logger = logging.getLogger(__name__)

DEFAULT_PER_PAGE = 20
RATE_LIMIT_BACKOFF = 5  # seconds


def _encode_project(project_id: str) -> str:
    """URL-encode a project path for use in API URLs.

    GitLab accepts URL-encoded namespace/project paths wherever a numeric ID
    is expected, e.g. ``mygroup%2Fmysubgroup%2Fmyproject``.
    """
    return quote(project_id, safe="")


@dataclass
class CodeSearchResult:
    project_id: str
    project_name: str
    file_path: str
    content: str
    ref: str
    url: str


class GitLabClient:
    """Client for the GitLab REST API v4.

    Authentication is done via the ``access_token`` query parameter
    (personal access token).
    """

    def __init__(self, config: GitLabConfig):
        self.config = config
        self._client = httpx.Client(
            base_url=config.base_url,
            headers={"PRIVATE-TOKEN": f"{config.api_token}"},
            timeout=30.0,
        )

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """Make an API request with rate-limit retry."""
        response = self._client.request(method, path, **kwargs)
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", RATE_LIMIT_BACKOFF))
            logger.warning("Rate limited, retrying in %ds...", retry_after)
            time.sleep(retry_after)
            response = self._client.request(method, path, **kwargs)
        response.raise_for_status()
        return response

    def _paginate(self, path: str, params: dict | None = None, max_pages: int = 5) -> list:
        """Fetch multiple pages of results."""
        params = dict(params or {})
        params.setdefault("per_page", DEFAULT_PER_PAGE)
        all_results = []

        for page in range(1, max_pages + 1):
            params["page"] = page
            response = self._request("GET", path, params=params)
            data = response.json()
            if not data:
                break
            all_results.extend(data)
            if len(data) < params["per_page"]:
                break

        return all_results

    def search_code(self, query: str, max_results: int = 10) -> list[CodeSearchResult]:
        """Search for code across all accessible projects."""
        logger.info("GitLab code search: %s", query)
        results = self._paginate(
            "/search",
            params={"scope": "blobs", "per_page": max_results},
            max_pages=1,
        )

        search_results = []
        for item in results[:max_results]:
            project_id = str(item.get("project_id", ""))
            file_path = item.get("path", item.get("filename", ""))
            ref = item.get("ref", "main")
            web_base = self.config.base_url.replace("/api/v4", "")
            project_path = item.get("project_path", "")
            if project_path:
                url = f"{web_base}/{project_path}/-/blob/{ref}/{file_path}"
            else:
                url = f"{web_base}/projects/{project_id}/repository/files/{file_path}"

            search_results.append(CodeSearchResult(
                project_id=project_id,
                project_name=item.get("project_name", project_path or project_id),
                file_path=file_path,
                content=item.get("data", ""),
                ref=ref,
                url=url,
            ))

        logger.info("Found %d code results", len(search_results))
        return search_results

    def search_project_code(
        self, project_id: str, query: str, max_results: int = 10
    ) -> list[CodeSearchResult]:
        """Search for code within a specific project."""
        logger.info("GitLab project code search in %s: %s", project_id, query)
        encoded = _encode_project(project_id)
        results = self._paginate(
            f"/projects/{encoded}/search",
            params={"scope": "blobs", "search": query, "per_page": max_results},
            max_pages=1,
        )

        search_results = []
        web_base = self.config.base_url.replace("/api/v4", "")
        for item in results[:max_results]:
            file_path = item.get("path", item.get("filename", ""))
            ref = item.get("ref", "main")
            url = f"{web_base}/{project_id}/-/blob/{ref}/{file_path}"

            search_results.append(CodeSearchResult(
                project_id=project_id,
                project_name=item.get("project_name", project_id),
                file_path=file_path,
                content=item.get("data", ""),
                ref=ref,
                url=url,
            ))

        logger.info("Found %d code results in %s", len(search_results), project_id)
        return search_results

    def get_project(self, project_id: str) -> dict:
        """Get project metadata. project_id can be 'group/subgroup/name'."""
        encoded = _encode_project(project_id)
        response = self._request("GET", f"/projects/{encoded}")
        return response.json()

    def get_file_tree(
        self, project_id: str, ref: str = "main", path: str = "", recursive: bool = True
    ) -> list[dict]:
        """Get the repository file tree. project_id can be 'group/subgroup/name'."""
        encoded = _encode_project(project_id)
        params = {"ref": ref, "recursive": str(recursive).lower()}
        if path:
            params["path"] = path
        return self._paginate(
            f"/projects/{encoded}/repository/tree",
            params=params,
            max_pages=20,
        )

    def get_file_content(self, project_id: str, file_path: str, ref: str = "main") -> str:
        """Get the raw content of a single file. project_id can be 'group/subgroup/name'."""
        encoded_project = _encode_project(project_id)
        encoded_path = quote(file_path, safe="")
        response = self._request(
            "GET",
            f"/projects/{encoded_project}/repository/files/{encoded_path}/raw",
            params={"ref": ref},
        )
        return response.text
