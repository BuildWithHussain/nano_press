import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import frappe


def _build_inventory_content(hostname: str, ssh_user: str, ssh_port: int) -> str:
	return f"""
[all]
{hostname} ansible_user={shlex.quote(ssh_user)} ansible_port={int(ssh_port)}
""".strip()


def _run_command(command: list[str]) -> str:
	process = subprocess.run(
		command,
		stdout=subprocess.PIPE,
		stderr=subprocess.STDOUT,
		text=True,
		check=False,
	)
	return process.stdout


def run_ad_hoc_ping(hostname: str, ssh_user: str, ssh_port: int) -> str:
	"""Run an ad-hoc ansible ping and return combined stdout.

	Uses the controller's default SSH key from ~/.ssh/.
	"""
	inventory_content = _build_inventory_content(hostname, ssh_user, ssh_port)

	with tempfile.TemporaryDirectory() as tmpdir:
		inventory_path = Path(tmpdir) / "inventory.ini"
		inventory_path.write_text(inventory_content, encoding="utf-8")

		# Ansible ad-hoc ping module
		cmd = [
			"ansible",
			"all",
			"-i",
			str(inventory_path),
			"-m",
			"ping",
			"-o",
		]

		output = _run_command(cmd)

		# Optionally gather facts for more detail
		setup_cmd = [
			"ansible",
			"all",
			"-i",
			str(inventory_path),
			"-m",
			"setup",
			"-a",
			"filter=ansible_distribution*",
			"-o",
		]
		output += "\n\n" + _run_command(setup_cmd)

	return output.strip()


def run_playbook(
	inventory_host: str,
	ssh_user: str,
	ssh_port: int,
	playbook_path: str,
	extra_vars: dict[str, str] | None = None,
	verbose: bool = True,
) -> str:
	"""Run an Ansible playbook against a single host using a temp inventory.

	extra_vars are passed as key=value pairs.
	"""
	inventory_content = _build_inventory_content(inventory_host, ssh_user, ssh_port)
	with tempfile.TemporaryDirectory() as tmpdir:
		inventory_path = Path(tmpdir) / "inventory.ini"
		inventory_path.write_text(inventory_content, encoding="utf-8")

		cmd: list[str] = [
			"ansible-playbook",
			"-i",
			str(inventory_path),
			playbook_path,
		]

		# Add verbose flag for better debugging
		if verbose:
			cmd.append("-vv")

		if extra_vars:
			for key, value in extra_vars.items():
				cmd.extend(["--extra-vars", f"{key}={value}"])

		# Log the command being executed for debugging

		playbook_name = Path(playbook_path).name
		if extra_vars:
			frappe.logger().debug(f"Extra vars: {extra_vars}")

		output = _run_command(cmd)

		# Add separator for better log readability
		return f"\n{'='*60}\nPlaybook: {playbook_name}\n{'='*60}\n{output}"
