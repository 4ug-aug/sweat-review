from pathlib import Path

import yaml

from preview_agent.compose import ComposeRenderer


class _ComposeLoader(yaml.SafeLoader):
    """SafeLoader that accepts Docker Compose custom tags like !override."""
    pass


_ComposeLoader.add_multi_constructor(
    "!", lambda loader, suffix, node: loader.construct_sequence(node)
    if isinstance(node, yaml.SequenceNode)
    else loader.construct_mapping(node)
    if isinstance(node, yaml.MappingNode)
    else loader.construct_scalar(node),
)


def _load(text: str) -> dict:
    return yaml.load(text, Loader=_ComposeLoader)


def test_render_override_contains_labels(compose_renderer: ComposeRenderer) -> None:
    result = compose_renderer.render_override(pr_number=42, vps_ip="10.0.0.5")
    assert "pr-42" in result
    assert "10.0.0.5.nip.io" in result
    assert "traefik.enable=true" in result


def test_render_override_valid_yaml(compose_renderer: ComposeRenderer) -> None:
    result = compose_renderer.render_override(pr_number=7, vps_ip="192.168.1.1")
    parsed = _load(result)
    assert "services" in parsed
    assert "nginx" in parsed["services"]
    assert "traefik-public" in parsed["networks"]
    assert parsed["networks"]["traefik-public"]["external"] is True


def test_render_override_has_networks(compose_renderer: ComposeRenderer) -> None:
    result = compose_renderer.render_override(pr_number=1, vps_ip="127.0.0.1")
    parsed = _load(result)
    nginx = parsed["services"]["nginx"]
    assert "default" in nginx["networks"]
    assert "traefik-public" in nginx["networks"]


def test_render_override_clears_ports(compose_renderer: ComposeRenderer) -> None:
    result = compose_renderer.render_override(pr_number=1, vps_ip="127.0.0.1")
    parsed = _load(result)
    nginx = parsed["services"]["nginx"]
    assert nginx["ports"] == []


def test_write_override_creates_file(
    compose_renderer: ComposeRenderer, tmp_path: Path
) -> None:
    path = compose_renderer.write_override(tmp_path, pr_number=10, vps_ip="1.2.3.4")
    assert path.exists()
    assert path.name == "docker-compose.override.yml"
    content = path.read_text()
    assert "pr-10" in content
    assert "1.2.3.4" in content
