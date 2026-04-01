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

    def render_override(self, pr_number: int, vps_ip: str) -> str:
        template = self._env.get_template(self._template_name)
        return template.render(pr_number=pr_number, vps_ip=vps_ip)

    def write_override(
        self, target_dir: Path, pr_number: int, vps_ip: str, compose_file: str = "docker-compose.yml"
    ) -> Path:
        override_content = self.render_override(pr_number, vps_ip)
        self._validate_target(target_dir, override_content, compose_file)
        output_path = target_dir / "docker-compose.override.yml"
        output_path.write_text(override_content)
        return output_path

    def _validate_target(self, target_dir: Path, override_content: str, compose_file: str) -> None:
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

        target_services = set(target["services"].keys())

        # Parse the override to find which services it references
        # Use a custom loader to handle Docker Compose tags like !override
        override = yaml.load(override_content, Loader=_ComposeLoader)
        if not isinstance(override, dict) or "services" not in override:
            return

        override_services = set(override["services"].keys())
        missing = override_services - target_services

        if missing:
            raise ComposeValidationError(
                f"Override references services not found in {compose_path.name}: "
                f"{', '.join(sorted(missing))}. "
                f"Available services: {', '.join(sorted(target_services))}. "
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
