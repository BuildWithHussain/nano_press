# Copyright (c) 2025, Venkatesh M and contributors
# For license information, please see license.txt

import os

import frappe
from frappe.model.document import Document
from frappe.utils import random_string

from nano_press.nano_press.utils.ansible.src.AnsibleRunner import AnsibleRunner


class FrappeSite(Document):
	def before_insert(self):
		self._ensure_password()

	def before_save(self):
		if self.docstatus == 1:
			return
		if self.is_custom and self.custom_image and self.has_value_changed("custom_image"):
			self._sync_apps_from_custom_image()

	def validate(self):
		self.validate_server()
		if self.docstatus == 0:
			self._ensure_password()

	def validate_server(self):
		linked_server = (self.server_name or "").strip()
		if not linked_server:
			frappe.throw("Please select a Server in this record before deploying.")
		if not frappe.db.exists("Server", linked_server):
			frappe.throw(f"Linked Server '{linked_server}' does not exist.")
		server = frappe.get_doc("Server", linked_server)
		if getattr(server, "verify_status", "Not Verified") != "Verified":
			frappe.throw("Server is not verified. Please verify the server first.")
		return server

	def _ensure_password(self):
		if not self.admin_password:
			self.admin_password = random_string(10)

		if self.ssl_enabled and not self.traefik_password:
			self.traefik_password = random_string(10)

	def _sync_apps_from_custom_image(self):
		self.set("install_apps", [])
		custom = frappe.get_doc("Custom Image", self.custom_image)
		for row in custom.apps_config:
			self.append("install_apps", {"app_name": row.app_name})

	def get_docker_image(self) -> str:
		"""Resolve the Docker image to use for deployment
		Returns the appropriate Docker image based on is_custom flag"""
		if self.is_custom and self.custom_image:
			custom_img = frappe.get_doc("Custom Image", self.custom_image)

			if custom_img.image_tag:
				return custom_img.image_tag

		return self.docker_image

	def get_deployment_vars(self) -> dict:
		"""Prepare all variables needed for deployment"""

		install_apps = [row.app_name for row in self.get("install_apps") if row.app_name]
		install_apps_csv = ",".join(install_apps) if install_apps else "erpnext"

		docker_image = self.get_docker_image()

		log_text = f"""
        === Deployment Configuration ===
        Docker Image: {docker_image}
        Site Name: {self.site_name}
        Apps to Install: {install_apps_csv}
        SSL Enabled: {'Yes' if self.ssl_enabled else 'No'}
        Custom Image: {'Yes - ' + docker_image if self.is_custom else 'No'}
        Admin Password: {'Set- ' if self.admin_password else 'admin'}
        Traefik Domain: {self.traefik_domain or ''}
        Traefik Email: {self.traefik_email or ''}
        ================================
        """.strip()

		self.append_log(log_text)

		return {
			"ssl_enabled": int(self.ssl_enabled or 0),
			"docker_image": docker_image,
			"site_name": self.site_name or "",
			"traefik_domain": self.traefik_domain or "",
			"traefik_email": self.traefik_email or "",
			"traefik_plain_password": self.traefik_password,
			"install_apps_csv": install_apps_csv,
			"admin_password": self.admin_password,
		}

	def append_log(self, text: str) -> None:
		frappe.db.sql(
			"""UPDATE `tabFrappe Site`
           SET deployment_log = CONCAT(%s, '\n', COALESCE(deployment_log, ''))
           WHERE name = %s""",
			(text, self.name),
		)

	def stream_deployment_update(self, log_line: str):
		"""Stream individual log line to UI in real-time.

		Args:
			log_line: Single line from deployment output
		"""
		try:
			# Send real-time notification to UI
			frappe.publish_realtime(
				event="frappe_site_live_update",
				message={
					"frappe_site": self.name,
					"log_line": log_line,
					"timestamp": frappe.utils.now_datetime(),
				},
				after_commit=False,
			)

			# Update document in database every 10 lines or on important lines
			self._line_count = getattr(self, "_line_count", 0) + 1

			# Update document for important lines or every 10 lines
			important = (
				self._line_count % 10 == 0  # Every 10 lines
				or "TASK" in log_line  # Ansible tasks
				or "Step" in log_line  # Docker steps
				or "ERROR" in log_line  # Errors
				or "FAILED" in log_line  # Failures
				or "ok:" in log_line  # Ansible success
				or "changed:" in log_line  # Ansible changes
				or "Creating" in log_line  # Container creation
				or "Starting" in log_line  # Container starting
				or "Installing" in log_line  # App installation
			)

			if important or (self._line_count % 20 == 0):
				frappe.db.sql(
					"""UPDATE `tabFrappe Site`
					   SET deployment_log = CONCAT(%s, '\n', COALESCE(deployment_log, ''))
					   WHERE name = %s""",
					(log_line + "\n", self.name),
				)

		except Exception as e:
			frappe.log_error(f"Failed to stream deployment update: {e!s}", "Deployment Streaming")

	def _trim_deployment_log(self, max_chars: int = 200_000):
		frappe.db.sql(
			"""UPDATE `tabFrappe Site`
			SET deployment_log = RIGHT(deployment_log, %s)
			WHERE name = %s AND CHAR_LENGTH(deployment_log) > %s""",
			(max_chars, self.name, max_chars),
		)

	def _playbooks_base(self) -> str:
		return frappe.get_app_path("nano_press", "nano_press", "utils", "ansible", "playbooks")

	def _run_playbook_and_stream(
		self,
		playbook_filename: str,
		*,
		extra_vars: dict | None = None,
		verbosity: int = 2,
		timeout: int = 60 * 20,
	):
		server = frappe.get_doc("Server", self.server_name)
		runner = AnsibleRunner()
		playbook_path = os.path.join(self._playbooks_base(), playbook_filename)

		out = runner.run_playbook_text(
			inventory_host=server.server_ip,
			ssh_user=(server.ssh_user or "root"),
			ssh_port=int(server.ssh_port or 22),
			playbook_path=playbook_path,
			verbosity=verbosity,
			timeout=timeout,
			extra_vars=extra_vars,
		)
		for line in out.splitlines():
			line = line.strip()
			if line:
				self.stream_deployment_update(line)

	@frappe.whitelist()
	def prepare_for_deployment(self) -> dict:
		self.validate_server()
		vars = self.get_deployment_vars()
		self.db_set("status", "Deploying", update_modified=False)

		try:
			self.stream_deployment_update("=== Installing Docker and Docker Compose ===")
			self._run_playbook_and_stream("install_docker.yml")

			self.stream_deployment_update("=== Preparing Frappe Docker Repository ===")
			self._run_playbook_and_stream("prepare_repo.yml")

			self.stream_deployment_update("=== Configuring Deployment Settings ===")
			self._run_playbook_and_stream("render_pwd.yml", extra_vars=vars)

			self.stream_deployment_update("=== Deployment Preparation Completed Successfully ===")
			self.db_set("status", "Ready To Deploy", update_modified=False)
			self.db_set("last_deployed_at", frappe.utils.now_datetime(), update_modified=False)
			return {"status": 200, "message": "Deployment prepared successfully"}

		except Exception as exc:
			msg = f"Deployment failed: {frappe.utils.cstr(exc)}"
			self.stream_deployment_update(f"ERROR: {msg}")
			self.append_log(msg)
			self.db_set("status", "Failed", update_modified=False)
			return {"status": 500, "message": frappe.utils.cstr(exc)}

	@frappe.whitelist()
	def deploy_site(self) -> dict:
		self.validate_server()
		try:
			self.stream_deployment_update("=== Starting Server Deployment ===")
			self.stream_deployment_update("Executing docker compose up...")
			self._run_playbook_and_stream("compose_up.yml", timeout=60 * 20)

			self.stream_deployment_update("=== Deployment Completed Successfully ===")
			self.db_set("status", "Deployed", update_modified=False)
			frappe.publish_realtime(
				event="frappe_site_update",
				message={
					"frappe_site": self.name,
					"status": "success",
					"message": "Deployment completed successfully",
				},
				after_commit=False,
			)
			return {"status": 200, "message": "Deployment completed successfully"}

		except Exception as exc:
			err = f"Deployment failed: {frappe.utils.cstr(exc)}"
			self.stream_deployment_update(f"ERROR: {err}")
			frappe.publish_realtime(
				event="frappe_site_update",
				message={"frappe_site": self.name, "status": "error", "message": err},
				after_commit=False,
			)
			self.db_set("status", "Failed", update_modified=False)
			return {"status": 500, "message": frappe.utils.cstr(exc)}

	@frappe.whitelist()
	def stop_site(self) -> dict:
		try:
			self.stream_deployment_update("=== Stopping all containers ===")
			self._run_playbook_and_stream("stop_all_containers.yml", timeout=60 * 15)

			self.append_log("All containers stop playbook executed.")
			self.db_set("status", "Stopped", update_modified=False)

			return {"status": 200, "message": "All containers stopped successfully"}

		except Exception as exc:
			frappe.log_error(frappe.get_traceback(), "stop_all_containers failed")
			err = f"Stop failed: {frappe.utils.cstr(exc)}"
			self.stream_deployment_update(f"ERROR: {err}")
			self.append_log(err)
			self.db_set("status", "Failed", update_modified=False)
			return {"status": 500, "message": frappe.utils.cstr(exc)}

	@frappe.whitelist()
	def queue_prepare_for_deployment(self):
		job = frappe.enqueue_doc(
			self.doctype,
			self.name,
			"prepare_for_deployment",
			queue="long",
			timeout=60 * 45,
			job_name=f"Prepare {self.name}",
		)
		return {"status": 202, "job_id": job.get_id()}

	@frappe.whitelist()
	def queue_deploy_site(self):
		job = frappe.enqueue_doc(
			self.doctype,
			self.name,
			"deploy_site",
			queue="long",
			timeout=60 * 45,
			job_name=f"Deploy {self.name}",
		)
		return {"status": 202, "job_id": job.get_id()}

	@frappe.whitelist()
	def queue_stop_all_containers(self):
		job = frappe.enqueue_doc(
			self.doctype,
			self.name,
			"stop_site",
			queue="short",
			timeout=60 * 20,
			job_name=f"Stop containers {self.name}",
		)
		return {"status": 202, "job_id": job.get_id()}
