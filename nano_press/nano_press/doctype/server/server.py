# Copyright (c) 2025, Venkatesh M and contributors
# For license information, please see license.txt

import os
import subprocess

import frappe
from frappe.model.document import Document

from nano_press.utils.ansible_runner import run_playbook


class Server(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		compose_installed: DF.Check
		compose_version: DF.Data | None
		docker_installed: DF.Check
		docker_version: DF.Data | None
		last_prepared_at: DF.Datetime | None
		last_verified_at: DF.Datetime | None
		server_ip: DF.Data
		server_name: DF.Data
		ssh_port: DF.Int
		ssh_user: DF.Data
		traefik_deployed: DF.Check
		traefik_domain: DF.Data
		traefik_email: DF.Data
		traefik_password: DF.Password
		traefik_username: DF.Data
		traefik_version: DF.Data | None
		verify_status: DF.Literal[
			"Not Verified", "Verifying", "Verified", "Failed", "Not Prepared", "Preparing", "Prepared"
		]
	# end: auto-generated types

	@staticmethod
	def _read_local_public_key() -> str | None:
		"""Attempt to read a usable SSH public key from standard locations.

		Returns the first available public key content, or None.
		"""
		candidate_paths = [
			os.path.expanduser(path)
			for path in [
				"~/.ssh/id_ed25519.pub",
				"~/.ssh/id_rsa.pub",
				"~/.ssh/id_ecdsa.pub",
				"~/.ssh/id_dsa.pub",
			]
		]
		for candidate in candidate_paths:
			try:
				if os.path.exists(candidate):
					with open(candidate) as fh:
						data = fh.read().strip()
						if data:
							return data
			except Exception:
				continue
		# Try deriving from private keys using ssh-keygen
		private_candidates = [
			os.path.expanduser(p)
			for p in [
				"~/.ssh/id_ed25519",
				"~/.ssh/id_rsa",
				"~/.ssh/id_ecdsa",
				"~/.ssh/id_dsa",
			]
		]
		for private_key in private_candidates:
			try:
				if os.path.exists(private_key):
					result = subprocess.run(
						["ssh-keygen", "-y", "-f", private_key],
						stdout=subprocess.PIPE,
						stderr=subprocess.DEVNULL,
						text=True,
						check=False,
					)
					pub = (result.stdout or "").strip()
					if pub:
						return pub
			except Exception:
				continue
		return None

	def prepare_server(self):
		result = run_playbook(host=self.server_ip, playbook_path="install_docker.yml", become=True)

		if not result.get("ok"):
			data = result.get("data", {})
			stderr = data.get("stderr", "Unknown error")
			error_msg = data.get("message", stderr)
			frappe.throw(f"Failed to install docker: {error_msg}")

		data = result.get("data", {})

		if data.get("stderr"):
			frappe.log_error(f"Docker installation stderr: {data.get('stderr')}", "Docker Install Warning")

		# Extract versions from Ansible playbook results
		docker_version = "Unknown"
		compose_version = "Unknown"

		# Parse through plays and tasks to find registered variables
		# The actual playbook results are in raw_json
		raw_json = data.get("raw_json", {})
		plays = raw_json.get("plays", [])

		for play in plays:
			tasks = play.get("tasks", [])
			for task in tasks:
				# Task name is in task["task"]["name"]
				task_info = task.get("task", {})
				task_name = task_info.get("name", "")
				hosts_data = task.get("hosts", {})

				# Get the first host's data (assuming single host execution)
				for _host, host_result in hosts_data.items():
					if task_name == "Get Docker version":
						docker_version = host_result.get("stdout", "").strip() or "Unknown"
					elif task_name == "Get Docker Compose version":
						compose_version = host_result.get("stdout", "").strip() or "Unknown"

		# Update server fields
		self.db_set("docker_installed", True)
		self.db_set("docker_version", docker_version)
		self.db_set("compose_installed", True)
		self.db_set("compose_version", compose_version)
		self.db_set("verify_status", "Prepared")
		self.db_set("last_prepared_at", frappe.utils.now_datetime())

		return {
			"status": 200,
			"message": f"Docker {docker_version} and Compose {compose_version} installed successfully",
			"log_id": result.get("log_id"),
			"docker_version": docker_version,
			"compose_version": compose_version,
		}

	def deploy_traefik(self):
		"""Deploy Traefik reverse proxy with Let's Encrypt SSL."""
		# Validate required fields
		if not self.traefik_domain:
			frappe.throw("Traefik domain is required")
		if not self.traefik_email:
			frappe.throw("Traefik email is required")
		if not self.traefik_username:
			frappe.throw("Traefik username is required")
		if not self.traefik_password:
			frappe.throw("Traefik password is required")

		# Prepare extra vars for the playbook
		extra_vars = {
			"traefik_domain": self.traefik_domain,
			"traefik_email": self.traefik_email,
			"traefik_username": self.traefik_username,
			"traefik_password": self.get_password("traefik_password"),
		}

		result = run_playbook(
			host=self.server_ip, playbook_path="install_traefik.yml", become=True, extra_vars=extra_vars
		)

		if not result.get("ok"):
			data = result.get("data", {})

			# Try multiple ways to extract error message
			error_msg = (
				data.get("message") or data.get("stderr_tail") or data.get("stderr") or "Unknown error"
			)

			# Get log_id for reference
			log_ref = f" (Check log: {result.get('log_id')})" if result.get("log_id") else ""

			# Log full response for debugging
			frappe.log_error(
				title="Traefik Deployment Failed",
				message=f"Server: {self.name}\nFull response: {frappe.as_json(result, indent=2)}",
			)

			frappe.throw(f"Failed to deploy Traefik: {error_msg}{log_ref}")

		data = result.get("data", {})

		if data.get("stderr"):
			frappe.log_error(f"Traefik deployment stderr: {data.get('stderr')}", "Traefik Deploy Warning")

		# Extract version info from raw_json
		traefik_version = "v2.11"  # Default from template
		raw_json = data.get("raw_json", {})
		plays = raw_json.get("plays", [])

		for play in plays:
			tasks = play.get("tasks", [])
			for task in tasks:
				task_info = task.get("task", {})
				task_name = task_info.get("name", "")
				hosts_data = task.get("hosts", {})

				for _host, host_result in hosts_data.items():
					if task_name == "Get Traefik version":
						traefik_version = host_result.get("stdout", "").strip() or traefik_version

		# Update server fields
		self.db_set("traefik_deployed", True)
		self.db_set("traefik_version", traefik_version)

		return {
			"status": 200,
			"message": f"Traefik {traefik_version} deployed successfully on {self.traefik_domain}",
			"log_id": result.get("log_id"),
			"traefik_version": traefik_version,
			"traefik_domain": self.traefik_domain,
		}


@frappe.whitelist()
def prepare_server(server_name: str):
	"""
	Whitelisted wrapper to prepare a server by installing Docker.

	Args:
		server_name: Name of the Server document

	Returns:
		dict with status, message, and log_id
	"""
	if not server_name:
		frappe.throw("Server name is required")

	server = frappe.get_doc("Server", server_name)
	return server.prepare_server()


@frappe.whitelist()
def deploy_traefik(server_name: str):
	"""
	Whitelisted wrapper to deploy Traefik reverse proxy on a server.

	Args:
		server_name: Name of the Server document

	Returns:
		dict with status, message, log_id, and traefik info
	"""
	if not server_name:
		frappe.throw("Server name is required")

	server = frappe.get_doc("Server", server_name)
	return server.deploy_traefik()


@frappe.whitelist()
def get_public_key_html() -> str:
	"""Render the server's local SSH public key as HTML instructions for the user.

	This reads a public key from the host running the Frappe app and returns an
	HTML snippet to show in the `public_key` HTML field.
	"""
	public_key = Server._read_local_public_key()
	if not public_key:
		return (
			'<div class="text-muted">No SSH public key found on the server. '
			"Ensure a key exists at ~/.ssh/id_ed25519.pub or ~/.ssh/id_rsa.pub.</div>"
		)

	html = f"""
        <div>
            <p><strong>Server Public Key</strong></p>
            <div style=\"margin: 6px 0;\">
                <button id=\"copy-public-key-btn\" type=\"button\" class=\"btn btn-sm btn-secondary\">Copy Public Key</button>
            </div>
            <pre id=\"server-public-key\" style=\"white-space: pre-wrap; word-break: break-all;\">{frappe.utils.escape_html(public_key)}</pre>
            <p>Copy the above key into <code>~/.ssh/authorized_keys</code> on your remote server.
            Ensure file permissions are correct and SSH is enabled for the configured user.</p>
        </div>
    """
	return html
