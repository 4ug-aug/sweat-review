import hashlib
import hmac

from preview_agent.github_client import GitHubClient


def _make_signature(secret: str, payload: bytes) -> str:
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_verify_signature_valid() -> None:
    client = GitHubClient(token="tok", repo="o/r", webhook_secret="mysecret")
    payload = b'{"action": "opened"}'
    sig = _make_signature("mysecret", payload)
    assert client.verify_signature(payload, sig) is True


def test_verify_signature_invalid() -> None:
    client = GitHubClient(token="tok", repo="o/r", webhook_secret="mysecret")
    payload = b'{"action": "opened"}'
    assert client.verify_signature(payload, "sha256=bad") is False


def test_verify_signature_wrong_format() -> None:
    client = GitHubClient(token="tok", repo="o/r", webhook_secret="mysecret")
    payload = b'{"action": "opened"}'
    assert client.verify_signature(payload, "md5=something") is False
