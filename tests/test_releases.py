import httpx2

from pixgen.releases import fetch_latest_release


def _client(handler) -> httpx2.Client:
    return httpx2.Client(transport=httpx2.MockTransport(handler))


class TestFetchLatestRelease:
    def test_returns_release(self) -> None:
        client = _client(
            lambda _request: httpx2.Response(
                200, json={"tag_name": "v0.2.0", "html_url": "https://example.test/r"}
            )
        )
        release = fetch_latest_release(client)
        assert release is not None
        assert release.tag == "v0.2.0"
        assert release.url == "https://example.test/r"

    def test_http_error_returns_none(self) -> None:
        assert fetch_latest_release(_client(lambda _r: httpx2.Response(403))) is None

    def test_malformed_payload_returns_none(self) -> None:
        assert fetch_latest_release(_client(lambda _r: httpx2.Response(200, json={}))) is None

    def test_invalid_json_returns_none(self) -> None:
        assert fetch_latest_release(_client(lambda _r: httpx2.Response(200, text="<html>"))) is None

    def test_connection_error_returns_none(self) -> None:
        def handler(request: httpx2.Request) -> httpx2.Response:
            raise httpx2.ConnectError("offline", request=request)

        assert fetch_latest_release(_client(handler)) is None
