from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader


class ComposeValidationError(Exception):
    pass


class ComposeRenderer:
    def __init__(self, template_path: Path) -> None:
        self._env = Environment(
            loader=FileSystemLoader(str(template_path.parent)),
            keep_trailing_newline=True,
        )
        self._template_name = template_path.name

    def render_override(
        self, pr_number: int, vps_ip: str, all_services: list[str] | None = None
    ) -> str:
        template = self._env.get_template(self._template_name)
        return template.render(
            pr_number=pr_number,
            vps_ip=vps_ip,
            all_services=all_services or [],
        )

    def write_override(
        self, target_dir: Path, pr_number: int, vps_ip: str, compose_file: str = "docker-compose.yml"
    ) -> Path:
        target_services = self._validate_target(target_dir, compose_file)
        override_content = self.render_override(pr_number, vps_ip, target_services)
        self._validate_override_services(override_content, target_services, compose_file)
        output_path = target_dir / "docker-compose.override.yml"
        output_path.write_text(override_content)
        return output_path

    def _validate_target(self, target_dir: Path, compose_file: str) -> list[str]:
        """Parse the target compose file and return its service names."""
        compose_path = target_dir / compose_file

        if not compose_path.exists():
            raise ComposeValidationError(
                f"{compose_file} not found in {target_dir}. "
                "Check your COMPOSE_FILE setting."
            )

        try:
            target = yaml.safe_load(compose_path.read_text())
        except yaml.YAMLError as exc:
            raise ComposeValidationError(
                f"Failed to parse {compose_path.name}: {exc}"
            ) from exc

        if not isinstance(target, dict) or "services" not in target:
            raise ComposeValidationError(
                f"{compose_path.name} has no 'services' section."
            )

        return sorted(target["services"].keys())

    def _validate_override_services(
        self, override_content: str, target_services: list[str], compose_file: str
    ) -> None:
        """Check that all services referenced in the override exist in the target."""
        override = yaml.load(override_content, Loader=_ComposeLoader)
        if not isinstance(override, dict) or "services" not in override:
            return

        override_services = set(override["services"].keys())
        target_set = set(target_services)
        missing = override_services - target_set

        if missing:
            raise ComposeValidationError(
                f"Override references services not found in {compose_file}: "
                f"{', '.join(sorted(missing))}. "
                f"Available services: {', '.join(sorted(target_set))}. "
                f"Update the override template or the target repo's Compose file."
            )


class _ComposeLoader(yaml.SafeLoader):
    pass


_ComposeLoader.add_multi_constructor(
    "!",
    lambda loader, suffix, node: (
        loader.construct_sequence(node)
        if isinstance(node, yaml.SequenceNode)
        else loader.construct_mapping(node)
        if isinstance(node, yaml.MappingNode)
        else loader.construct_scalar(node)
    ),
)
