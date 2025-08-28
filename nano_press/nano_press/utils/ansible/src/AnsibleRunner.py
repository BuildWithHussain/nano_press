# nano_press/nano_press/utils/ansible_runner.py

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import frappe


@dataclass(frozen=True)
class RunResult:
	cmd: list[str]
	rc: int
	stdout: str
	stderr: str
	duration_sec: float
	playbook: str | None = None

	def banner_text(self) -> str:
		name = self.playbook or "ad-hoc"
		top = "=" * 60
		body = f"\n{top}\nPlaybook: {name} (rc={self.rc})\n{top}\n{self.stdout}"
		if self.stderr:
			body += f"\n{'-'*60}\nSTDERR:\n{self.stderr}"
		return body


class AnsibleError(Exception):
	"""Wrapper exception for Ansible execution problems."""


class AnsibleRunner:
	"""
	OOP runner for Ansible ad-hoc and playbook executions.
	- Safe inventory generation (temp file).
	- Extra vars via JSON file (type-safe, quoting-safe).
	- Redacted logs (no secrets in logs).
	- Verbosity, become, private key, timeout, env overrides.
	"""

	_SENSITIVE_KEYS = ("password", "passwd", "secret", "token", "api_key", "access_key", "secret_key", "key")

	def __init__(
		self,
		*,
		host_key_checking: bool = False,
		default_timeout: int = 60 * 30,
		logger_name: str = "nano_press.ansible",
		ansible_playbook_bin: str | None = None,
		ansible_bin: str | None = None,
	) -> None:
		self.logger = frappe.logger(logger_name)
		self.default_timeout = int(default_timeout)

		# Resolve binaries early with a friendly error if missing
		self.ansible_playbook_bin = ansible_playbook_bin or shutil.which("ansible-playbook")
		self.ansible_bin = ansible_bin or shutil.which("ansible")

		if not self.ansible_playbook_bin:
			frappe.throw("ansible-playbook is not installed or not in PATH.")
		if not self.ansible_bin:
			frappe.throw("ansible is not installed or not in PATH.")

		# Base environment for subprocesses
		self.base_env = os.environ.copy()
		# Disable/enable host key checking
		self.base_env["ANSIBLE_HOST_KEY_CHECKING"] = "True" if host_key_checking else "False"
		# You can enable JSON callback if you plan to parse:
		# self.base_env.setdefault("ANSIBLE_STDOUT_CALLBACK", "json")

	# -------------------------
	# public API
	# -------------------------

	def run_ad_hoc_ping(
		self,
		hostname: str,
		ssh_user: str,
		ssh_port: int,
		*,
		timeout: int | None = None,
		facts_filter: str | None = "ansible_distribution*",
		verbosity: int | bool = 0,
		private_key: str | None = None,
	) -> RunResult:
		"""
		ansible -m ping, optionally followed by setup facts filtered selection.

		Args:
			hostname (str): Target host.
			ssh_user (str): SSH username.
			ssh_port (int): SSH port.
			timeout (Optional[int], optional): Timeout in seconds. Defaults to None.
			facts_filter (Optional[str], optional): Filter for setup facts. Defaults to "ansible_distribution*".
			verbosity (int | bool, optional): Verbosity level. Defaults to 0.
			private_key (Optional[str], optional): Path to private key. Defaults to None.

		Returns:
			RunResult: The result of the ad-hoc run. The `playbook` field is set to `None` for ad-hoc runs.
		"""
		with self._temp_inventory(hostname, ssh_user, ssh_port) as inv_path:
			cmds: list[list[str]] = [
				self._ansible_cmd(inv_path, "ping", verbosity, private_key),
			]

			if facts_filter:
				cmds.append(
					self._ansible_cmd(
						inv_path, "setup", verbosity, private_key, args=f"filter={facts_filter}"
					)
				)

			# Run sequentially and concatenate outputs
			all_out, all_err, last_rc, dur = [], [], 0, 0.0
			for _idx, cmd in enumerate(cmds):
				res = self._run(cmd, timeout or self.default_timeout)
				all_out.append(res.stdout)
				all_err.append(res.stderr)
				last_rc = res.rc
				dur += res.duration_sec

			# Aggregate all commands for clarity
			all_cmds = [c for c in cmds]

			return RunResult(
				cmd=[item for sublist in all_cmds for item in sublist],
				rc=last_rc,
				stdout="\n\n".join(all_out).strip(),
				stderr="\n\n".join(e for e in all_err if e).strip(),
				duration_sec=dur,
				playbook=None,
			)

	def run_playbook(
		self,
		*,
		inventory_host: str,
		ssh_user: str,
		ssh_port: int,
		playbook_path: str,
		extra_vars: Mapping[str, Any] | None = None,
		verbosity: int | bool = 0,
		timeout: int | None = None,
		become: bool = False,
		become_user: str | None = None,
		private_key: str | None = None,
		env: Mapping[str, str] | None = None,
		check: bool = False,
		diff: bool = False,
	) -> RunResult:
		"""
		Run a playbook with a temporary one-host inventory.

		Returns a RunResult. If you need the old string banner, call `.banner_text()` on the result.
		"""
		playbook_path = str(playbook_path)
		playbook_name = Path(playbook_path).name

		with (
			self._temp_inventory(inventory_host, ssh_user, ssh_port) as inv_path,
			self._temp_vars(extra_vars) as vars_path,
		):
			cmd: list[str] = [self.ansible_playbook_bin, "-i", str(inv_path), playbook_path]

			v = self._normalize_verbosity(verbosity)
			if v:
				cmd.append("-" + "v" * v)
			if become:
				cmd.append("--become")
			if become_user:
				cmd.extend(["--become-user", str(become_user)])
			if private_key:
				cmd.extend(["--private-key", str(private_key)])
			if check:
				cmd.append("--check")
			if diff:
				cmd.append("--diff")
			if vars_path:
				cmd.extend(["--extra-vars", f"@{vars_path}"])

			# Redacted metadata for logs
			self.logger.info(
				{
					"action": "run_playbook",
					"playbook": playbook_name,
					"cmd": cmd,
					"extra_vars": self._redact(extra_vars),
				}
			)

			# Merge env
			env_combined = self.base_env.copy()
			if env:
				env_combined.update(env)

			res = self._run(
				cmd, timeout or self.default_timeout, cwd=str(Path(playbook_path).parent), env=env_combined
			)
			return RunResult(
				cmd=res.cmd,
				rc=res.rc,
				stdout=res.stdout,
				stderr=res.stderr,
				duration_sec=res.duration_sec,
				playbook=playbook_name,
			)

	# -------------------------
	# compatibility helpers
	# -------------------------

	def run_playbook_text(self, **kwargs) -> str:
		"""
			Convenience wrapper returning the legacy bannered string.
			Usage compatibility with your current controller:
			    output = runner.run_playbook_text(
		def _normalize_verbosity(self, verbosity: Union[int, bool]) -> int:
			    )
		"""
		return self.run_playbook(**kwargs).banner_text()

	# -------------------------
	# internals
	# -------------------------

	def _normalize_verbosity(self, verbosity: int | bool) -> int:
		if isinstance(verbosity, bool):
			return 2 if verbosity else 0
		try:
			return max(0, min(4, int(verbosity)))
		except Exception:
			return 0

	def _redact(self, data: Mapping[str, Any] | None) -> Mapping[str, Any]:
		if not data:
			return {}
		masked: dict[str, Any] = {}
		for k, v in data.items():
			masked[k] = "******" if any(s in k.lower() for s in self._SENSITIVE_KEYS) else v
		return masked

	from contextlib import contextmanager

	@contextmanager
	def _temp_inventory(self, hostname: str, ssh_user: str, ssh_port: int):
		"""
		Create a temp inventory.ini and yield its path. Cleans up automatically.
		"""
		content = self._build_inventory_content(hostname, ssh_user, ssh_port)
		with tempfile.TemporaryDirectory() as tmpdir:
			inv = Path(tmpdir) / "inventory.ini"
			inv.write_text(content, encoding="utf-8")
			yield inv

	@contextmanager
	def _temp_vars(self, extra_vars: Mapping[str, Any] | None):
		"""
		Write extra_vars to a JSON file and yield its path. Yields None if no vars.
		"""
		if not extra_vars:
			yield None
			return
		with tempfile.TemporaryDirectory() as tmpdir:
			p = Path(tmpdir) / "vars.json"
			# Ensure JSON serializable
			p.write_text(json.dumps(extra_vars, ensure_ascii=False), encoding="utf-8")
			yield p

	def _build_inventory_content(self, hostname: str, ssh_user: str, ssh_port: int) -> str:
		return (
			"[all]\n" f"{hostname} ansible_user={shlex.quote(ssh_user)} ansible_port={int(ssh_port)}\n"
		).strip()

	@dataclass(frozen=True)
	class _ProcResult:
		cmd: list[str]
		rc: int
		stdout: str
		stderr: str
		duration_sec: float

	def _run(
		self,
		cmd: list[str],
		timeout: int,
		*,
		cwd: str | None = None,
		env: Mapping[str, str] | None = None,
	) -> _ProcResult:
		start = time.time()
		try:
			proc = subprocess.run(
				cmd,
				cwd=cwd,
				env=env or self.base_env,
				capture_output=True,
				text=True,
				timeout=timeout,
				check=False,
			)
		except subprocess.TimeoutExpired as e:
			frappe.log_error(frappe.get_traceback(), "Ansible timeout")
			# Surface a friendly text, but retain structure
			stdout = (e.output or "") + "\n[ERROR] Timed out."
			stderr = e.stderr or ""
			return self._ProcResult(
				cmd=cmd, rc=124, stdout=stdout, stderr=stderr, duration_sec=time.time() - start
			)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Ansible execution error")
			raise AnsibleError("Failed to execute Ansible command")

		return self._ProcResult(
			cmd=cmd,
			rc=proc.returncode,
			stdout=proc.stdout or "",
			stderr=proc.stderr or "",
			duration_sec=time.time() - start,
		)
