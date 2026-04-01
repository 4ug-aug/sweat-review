from pathlib import Path

from jinja2 import Environment, FileSystemLoader


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

    def write_override(self, target_dir: Path, pr_number: int, vps_ip: str) -> Path:
        content = self.render_override(pr_number, vps_ip)
        output_path = target_dir / "docker-compose.override.yml"
        output_path.write_text(content)
        return output_path
