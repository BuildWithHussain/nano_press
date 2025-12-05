from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import tempfile
import time
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import frappe


@dataclass(frozen=True)
class RunResult:
	cmd: list[str]
	rc: int
	stdout: str
	stderr: str
	duration_s: float
	playbook: str | None = None

	def to_json(self) -> str:
		return json.dumps(asdict(self), ensure_ascii=False, indent=2)


class AnsibleError(Exception):
	"""Raised when an Ansible execution fails fatally."""


class AnsibleOps:
	def __init__(
		self,
		*,
		host_key_checking: bool = False,
		ansible_playbook_bin: str | None = None,
		ansible_bin: str | None = None,
		default_timeout: int = 1800,
	):
		self.ansible_playbook_bin = ansible_playbook_bin or shutil.which("ansible-playbook")
		self.ansible_bin = ansible_bin or shutil.which("ansible")

		if not self.ansible_playbook_bin:
			raise FileNotFoundError("ansible-playbook not found in PATH.")
		if not self.ansible_bin:
			raise FileNotFoundError("ansible not found in PATH.")

		self.base_env = os.environ.copy()
		self.base_env["ANSIBLE_HOST_KEY_CHECKING"] = "True" if host_key_checking else "False"
		self.base_env["ANSIBLE_STDOUT_CALLBACK"] = "json"
		self.base_env.setdefault("ANSIBLE_LOAD_CALLBACK_PLUGINS", "True")
		self.default_timeout = default_timeout

	def run_playbook(
		self,
		*,
		host: str | None = None,
		user: str | None = None,
		port: int | None = None,
		server_ip: str | None = None,
		server_name: str | None = None,
		playbook_path: str,
		private_key: str | None = None,
		extra_vars: Mapping[str, Any] | None = None,
		become: bool = False,
		become_user: str | None = None,
		timeout: int | None = None,
	) -> dict[str, Any]:
		if not host:
			host, resolved_user, resolved_port, resolved_key = self._get_server_conn(
				server_ip=server_ip, server_name=server_name
			)
			user = user or resolved_user
			port = port or resolved_port
			private_key = private_key or resolved_key

		if not host or not user or port is None:
			frappe.throw("Insufficient connection details: host/user/port are required.")

		playbook_abs = self._resolve_playbook_path(playbook_path)

		with self._temp_inventory(host, user, int(port)) as inv, self._temp_vars(extra_vars) as vars_file:
			cmd = [self.ansible_playbook_bin, "-i", str(inv), playbook_abs]

			if become:
				cmd.append("--become")
			if become_user:
				cmd.extend(["--become-user", become_user])
			if private_key:
				cmd.extend(["--private-key", str(private_key)])
			if vars_file:
				cmd.extend(["--extra-vars", f"@{vars_file}"])

			start = time.time()
			rc, out, err = self._run(cmd, timeout or self.default_timeout)
			duration = round(time.time() - start, 3)

			return self._to_structured_json(
				cmd=cmd,
				rc=rc,
				stdout=out,
				stderr=err,
				duration_s=duration,
				operation="playbook",
				meta={
					"host": host,
					"user": user,
					"port": port,
					"playbook": playbook_abs,
					"source_playbook_arg": playbook_path,
					"server_ip": server_ip,
					"server_name": server_name,
				},
			)

	def run_ping(
		self,
		*,
		host: str | None = None,
		user: str | None = None,
		port: int | None = None,
		server_ip: str | None = None,
		server_name: str | None = None,
		private_key: str | None = None,
		timeout: int | None = None,
	) -> dict[str, Any]:
		"""Simple Ansible ping module."""

		if not host:
			host, resolved_user, resolved_port, resolved_key = self._get_server_conn(
				server_ip=server_ip, server_name=server_name
			)
			user = user or resolved_user
			port = port or resolved_port
			private_key = private_key or resolved_key

		if not host or not user or port is None:
			frappe.throw("Insufficient connection details: host/user/port are required.")

		with self._temp_inventory(host, user, int(port)) as inv:
			cmd = [self.ansible_bin, "all", "-i", str(inv), "-m", "ping"]
			if private_key:
				cmd.extend(["--private-key", str(private_key)])
			start = time.time()
			rc, out, err = self._run(cmd, timeout or 30)
			duration = round(time.time() - start, 3)
			return self._to_structured_json(
				cmd=cmd,
				rc=rc,
				stdout=out,
				stderr=err,
				duration_s=duration,
				operation="ping",
				meta={
					"host": host,
					"user": user,
					"port": port,
					"server_ip": server_ip,
					"server_name": server_name,
				},
			)

	# ---------------------
	# Internal helpers
	# ---------------------

	def _run(self, cmd: list[str], timeout: int) -> tuple[int, str, str]:
		try:
			proc = subprocess.run(
				cmd,
				capture_output=True,
				text=True,
				timeout=timeout,
				env=self.base_env,
			)
			return proc.returncode, proc.stdout, proc.stderr
		except subprocess.TimeoutExpired:
			return 124, "", "[TIMEOUT] Command exceeded timeout."
		except Exception as e:
			raise AnsibleError(f"Execution failed: {e}")

	@contextmanager
	def _temp_inventory(self, host: str, user: str, port: int):
		content = f"[all]\n{host} ansible_user={shlex.quote(user)} ansible_port={int(port)}\n"
		with tempfile.TemporaryDirectory() as tmpdir:
			path = Path(tmpdir) / "inventory.ini"
			path.write_text(content)
			yield path

	@contextmanager
	def _temp_vars(self, extra_vars: Mapping[str, Any] | None):
		if not extra_vars:
			yield None
			return
		with tempfile.TemporaryDirectory() as tmpdir:
			path = Path(tmpdir) / "vars.json"
			path.write_text(json.dumps(extra_vars))
			yield path

	# ---------------------
	# Structured JSON output
	# ---------------------

	def _to_structured_json(
		self,
		*,
		cmd: list[str],
		rc: int,
		stdout: str,
		stderr: str,
		duration_s: float,
		operation: str,
		meta: dict[str, Any],
	) -> dict[str, Any]:
		"""Normalize Ansible outputs into a clean JSON schema."""
		try:
			ansible_json = json.loads(stdout)
		except Exception:
			ansible_json = {}

		summary = ansible_json.get("stats") or ansible_json.get("summary") or {}
		ok = rc == 0 and not summary.get("failures", 0)

		return {
			"ok": ok,
			"operation": operation,
			"duration_s": duration_s,
			"meta": meta,
			"rc": rc,
			"summary": summary,
			"stdout_tail": stdout[-2000:],
			"stderr_tail": stderr[-2000:],
			"raw_json": ansible_json,
		}

	def _playbooks_base(self) -> str:
		return frappe.get_app_path("nano_press", "nano_press", "utils", "ansible", "playbooks")

	def _get_server_conn(
		self,
		*,
		server_ip: str | None = None,
		server_name: str | None = None,
		prefer_field_private_key: bool = True,
	) -> tuple[str, str, int, str | None]:
		"""
		Resolve host, user, port, private_key from the Server doctype.
		You can pass either server_ip or server_name.
		Returns: (host, user, port, private_key_path_or_None)
		"""
		if not (server_ip or server_name):
			frappe.throw("Pass either server_ip or server_name to resolve connection details.")

		filters = {"server_ip": server_ip} if server_ip else {"server_name": server_name}
		row = frappe.db.get_value(
			"Server",
			filters,
			["server_ip", "ssh_user", "ssh_port"],
			as_dict=True,
		)
		if not row:
			frappe.throw(f"Server not found for filter: {filters}")

		host = row.get("server_ip") or server_ip
		user = row.get("ssh_user") or "frappe"
		port = int(row.get("ssh_port") or 22)

		private_key = None
		if prefer_field_private_key:
			private_key = row.get("ssh_private_key_path") or row.get("private_key_path")

		return host, user, port, private_key

	def _resolve_playbook_path(self, playbook: str) -> str:
		"""
		Accepts either an absolute path or a short name like 'prepare' or 'prepare.yml'.
		Returns an absolute, existing path under the app's playbooks base if needed.
		"""
		if os.path.isabs(playbook) and os.path.isfile(playbook):
			return playbook

		candidate = playbook if os.path.splitext(playbook)[1] else f"{playbook}.yml"

		base = self._playbooks_base()
		full = os.path.join(base, candidate)
		if os.path.isfile(full):
			return full

		raise FileNotFoundError(f"Playbook not found: {playbook} (looked in {base})")
