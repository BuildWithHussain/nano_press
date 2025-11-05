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

	def validate(self):
		if not self.traefik_email:
			self.traefik_email = frappe.session.user
		self.created_by = frappe.session.user
		# Set server_name to the document name
		if self.name:
			self.server_name = self.name

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

	def prepare_server(self, include_traefik=False):
		"""
		Unified server preparation that installs Docker, Docker Compose, and optionally Traefik.
		Checks if components are already installed before attempting installation.

		Args:
			include_traefik: Whether to also deploy Traefik (default: False, requires traefik fields to be set)
		"""
		# Prepare extra vars for the playbook
		extra_vars = {}

		# Add Traefik configuration if requested and available
		if include_traefik:
			if not self.traefik_domain:
				frappe.throw("Traefik domain is required for Traefik deployment")
			if not self.traefik_email:
				frappe.throw("Traefik email is required for Traefik deployment")
			if not self.traefik_username:
				frappe.throw("Traefik username is required for Traefik deployment")
			if not self.traefik_password:
				frappe.throw("Traefik password is required for Traefik deployment")

			extra_vars = {
				"traefik_domain": self.traefik_domain,
				"traefik_email": self.traefik_email,
				"traefik_username": self.traefik_username,
				"traefik_password": self.get_password("traefik_password"),
			}

		# Run the unified preparation playbook
		result = run_playbook(
			host=self.server_ip,
			playbook_path="prepare_server.yml",
			become=True,
			extra_vars=extra_vars if extra_vars else None,
		)

		if not result.get("ok"):
			data = result.get("data", {})
			error_msg = (
				data.get("message") or data.get("stderr_tail") or data.get("stderr") or "Unknown error"
			)

			# Log the full response for debugging
			log_ref = f" (Check log: {result.get('log_id')})" if result.get("log_id") else ""
			frappe.log_error(
				title="Server Preparation Failed",
				message=f"Server: {self.name}\nFull response: {frappe.as_json(result, indent=2)}",
			)

			frappe.throw(f"Failed to prepare server: {error_msg}{log_ref}")

		data = result.get("data", {})

		if data.get("stderr"):
			frappe.log_error(f"Server preparation stderr: {data.get('stderr')}", "Server Preparation Warning")

		# Extract versions from Ansible playbook results
		docker_version = "Unknown"
		compose_version = "Unknown"
		traefik_version = None

		# Parse through plays and tasks to find registered variables
		raw_json = data.get("raw_json", {})
		plays = raw_json.get("plays", [])

		for play in plays:
			tasks = play.get("tasks", [])
			for task in tasks:
				task_info = task.get("task", {})
				task_name = task_info.get("name", "")
				hosts_data = task.get("hosts", {})

				# Get the first host's data (assuming single host execution)
				for _host, host_result in hosts_data.items():
					if task_name == "Get Docker version":
						docker_version = host_result.get("stdout", "").strip() or "Unknown"
					elif task_name == "Get Docker Compose version":
						compose_version = host_result.get("stdout", "").strip() or "Unknown"
					elif task_name == "Get Traefik version":
						traefik_version = host_result.get("stdout", "").strip() or "v2.11"

		# Update server fields for Docker
		self.db_set("docker_installed", True)
		self.db_set("docker_version", docker_version)
		self.db_set("compose_installed", True)
		self.db_set("compose_version", compose_version)
		self.db_set("verify_status", "Prepared")
		self.db_set("last_prepared_at", frappe.utils.now_datetime())

		# Update Traefik fields if it was deployed
		if include_traefik and traefik_version:
			self.db_set("traefik_deployed", True)
			self.db_set("traefik_version", traefik_version)

		response = {
			"status": 200,
			"message": "Server prepared successfully",
			"log_id": result.get("log_id"),
			"docker_version": docker_version,
			"compose_version": compose_version,
		}

		if include_traefik and traefik_version:
			response["traefik_version"] = traefik_version
			response["traefik_domain"] = self.traefik_domain
			response["message"] = (
				f"Server prepared with Docker {docker_version}, Compose {compose_version}, and Traefik {traefik_version}"
			)
		else:
			response["message"] = (
				f"Server prepared with Docker {docker_version} and Compose {compose_version}"
			)

		return response


@frappe.whitelist()
def prepare_server(server_name: str, include_traefik: bool = False):
	"""
	Whitelisted wrapper to prepare a server by installing Docker, Docker Compose, and optionally Traefik.

	Args:
		server_name: Name of the Server document
		include_traefik: Whether to also deploy Traefik (default: False)

	Returns:
		dict with status, message, versions, and log_id
	"""
	if not server_name:
		frappe.throw("Server name is required")

	server = frappe.get_doc("Server", server_name)
	return server.prepare_server(include_traefik=include_traefik)


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
