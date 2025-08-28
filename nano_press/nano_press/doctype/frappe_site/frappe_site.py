# Copyright (c) 2025, Venkatesh M and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import random_string


class FrappeSite(Document):
	def before_insert(self):
		self._ensure_password()

	def before_save(self):
		if self.is_custom and self.custom_image and self.has_value_changed("custom_image"):
			self._sync_apps_from_custom_image()

	def validate(self):
		self.server = self.validate_server()
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
		admin_password = self.admin_password
		traefik_password = self.traefik_password

		# Build apps CSV
		install_apps = [row.app_name for row in self.get("install_apps") if row.app_name]
		install_apps_csv = ",".join(install_apps) if install_apps else "erpnext"

		# Resolve Docker image
		docker_image = self.get_docker_image()

		# Log the deployment configuration
		log_text = f"""
        === Deployment Configuration ===
        Docker Image: {docker_image}
        Site Name: {self.site_name}
        Apps to Install: {install_apps_csv}
        SSL Enabled: {'Yes' if self.ssl_enabled else 'No'}
        Custom Image: {'Yes - ' + docker_image if self.is_custom else 'No'}
        Admin Password: {'Set- ' + self.admin_password if self.admin_password else 'admin'}
        Traefik Domain: {self.traefik_domain or ''}
        Traefik Email: {self.traefik_email or ''}
        ================================
        """
		self.append_log(log_text)

		deployment_vars = {
			"ssl_enabled": int(self.ssl_enabled or 0),
			"docker_image": docker_image,
			"site_name": self.site_name or "",
			"traefik_domain": self.traefik_domain or "",
			"traefik_email": self.traefik_email or "",
			"traefik_plain_password": traefik_password,
			"install_apps_csv": install_apps_csv,
			"admin_password": admin_password,
		}
		return deployment_vars

	def append_log(self, text: str) -> None:
		existing = self.get("deployment_log") or ""
		self.deployment_log = (text + "\n" + existing).strip()
		self.save(ignore_version=True)
		frappe.db.commit()

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
			)

			# Update document in database every 10 lines or on important lines
			if hasattr(self, "_line_count"):
				self._line_count += 1
			else:
				self._line_count = 1

			# Update document for important lines or every 10 lines
			should_update_doc = (
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

			if should_update_doc:
				# Update Deploy Server document with accumulated log lines
				frappe.db.sql(
					"""UPDATE `tabDeploy Server`
					   SET deployment_log = CONCAT(COALESCE(deployment_log, ''), %s)
					   WHERE name = %s""",
					(log_line + "\n", self.name),
				)
				frappe.db.commit()

		except Exception as e:
			# Don't break deployment process if streaming fails
			frappe.log_error(f"Failed to stream deployment update: {e!s}", "Deployment Streaming")

	@frappe.whitelist()
	def stop_all_containers(self) -> dict:
		server = frappe.get_doc("Server", self.server_name)
		from nano_press.nano_press.utils.ansible.src.AnsibleRunner import AnsibleRunner

		runner = AnsibleRunner()
		playbook_path = str(
			frappe.get_app_path(
				"nano_press",
				"nano_press",
				"utils",
				"ansible",
				"playbooks",
				"stop_all_containers.yml",
			)
		)

		try:
			# Execute with safe JSON extra-vars (none needed here), with verbosity and timeout
			output_text = runner.run_playbook_text(
				inventory_host=server.server_ip,
				ssh_user=(server.ssh_user or "root"),
				ssh_port=int(server.ssh_port or 22),
				playbook_path=playbook_path,
				verbosity=2,  # -vv
				timeout=60 * 15,  # 15 minutes
			)

			# Append logs (use your append_log; ideally it does db.set_value under the hood)
			if hasattr(self, "append_log"):
				self.append_log(output_text)

			frappe.db.set_value(self.doctype, self.name, "status", "Stopped", update_modified=False)

			return {"status": 200, "message": "All containers stopped successfully"}

		except Exception as exc:
			frappe.log_error(frappe.get_traceback(), "stop_all_containers failed")
			if hasattr(self, "append_log"):
				self.append_log(f"Stop failed: {frappe.utils.cstr(exc)}")
			frappe.db.set_value(self.doctype, self.name, "status", "Failed", update_modified=False)
			return {"status": 500, "message": frappe.utils.cstr(exc)}

	@frappe.whitelist()
	def prepare_for_deployment(self) -> dict:
		server = self.validate_server()
		deployment_vars = self.get_deployment_vars()
		try:
			self.status = "Deploying"
			self.save(ignore_version=True)
			frappe.db.commit()

			from nano_press.nano_press.utils.ansible_runner import run_playbook

			# 1) Install Docker + Compose v2
			self.stream_deployment_update("=== Installing Docker and Docker Compose ===")
			output = run_playbook(
				inventory_host=server.server_ip,
				ssh_user=(server.ssh_user or "root"),
				ssh_port=int(server.ssh_port or 22),
				playbook_path=str(
					frappe.get_app_path(
						"nano_press",
						"nano_press",
						"utils",
						"ansible",
						"playbooks",
						"install_docker.yml",
					)
				),
			)
			# Stream output line by line
			for line in output.split("\n"):
				if line.strip():
					self.stream_deployment_update(line.strip())

			# 2) Prepare repo
			self.stream_deployment_update("=== Preparing Frappe Docker Repository ===")
			output = run_playbook(
				inventory_host=server.server_ip,
				ssh_user=(server.ssh_user or "root"),
				ssh_port=int(server.ssh_port or 22),
				playbook_path=str(
					frappe.get_app_path(
						"nano_press",
						"nano_press",
						"utils",
						"ansible",
						"playbooks",
						"prepare_repo.yml",
					)
				),
			)
			# Stream output line by line
			for line in output.split("\n"):
				if line.strip():
					self.stream_deployment_update(line.strip())

			# 3) Render pwd.yml and .env on remote from Deploy Site data
			self.stream_deployment_update("=== Configuring Deployment Settings ===")
			output = run_playbook(
				inventory_host=server.server_ip,
				ssh_user=(server.ssh_user or "root"),
				ssh_port=int(server.ssh_port or 22),
				playbook_path=str(
					frappe.get_app_path(
						"nano_press",
						"nano_press",
						"utils",
						"ansible",
						"playbooks",
						"render_pwd.yml",
					)
				),
				extra_vars=deployment_vars,
			)
			# Stream output line by line
			for line in output.split("\n"):
				if line.strip():
					self.stream_deployment_update(line.strip())

			self.stream_deployment_update("=== Deployment Preparation Completed Successfully ===")
			self.status = "Ready To Deploy"
			self.last_deployed_at = frappe.utils.now_datetime()
			self.save(ignore_version=True)
			frappe.db.commit()
			return {"status": 200, "message": "Deployment prepared successfully"}
		except Exception as exc:
			error_msg = f"Deployment failed: {frappe.utils.cstr(exc)}"
			self.stream_deployment_update(f"ERROR: {error_msg}")
			self.append_log(error_msg)

			self.status = "Failed"
			self.save(ignore_version=True)
			frappe.db.commit()
			return {"status": 500, "message": frappe.utils.cstr(exc)}

	@frappe.whitelist()
	def frappe_site(self) -> dict:
		server = self.validate_server()
		from nano_press.nano_press.utils.ansible.src.AnsibleRunner import AnsibleRunner

		runner = AnsibleRunner()

		playbook_path = str(
			frappe.get_app_path(
				"nano_press",
				"nano_press",
				"utils",
				"ansible",
				"playbooks",
				"compose_up.yml",
			)
		)

		try:
			self.stream_deployment_update("=== Starting Server Deployment ===")
			self.stream_deployment_update("Executing docker compose up...")

			output_text = runner.run_playbook_text(
				inventory_host=server.server_ip,
				ssh_user=(server.ssh_user or "root"),
				ssh_port=int(server.ssh_port or 22),
				playbook_path=playbook_path,
				verbosity=2,  # -vv
				timeout=60 * 20,  # 20 minutes; tune for your infra
			)

			# Stream output line by line
			for line in output_text.split("\n"):
				if line.strip():
					self.stream_deployment_update(line.strip())

			self.stream_deployment_update("=== Deployment Completed Successfully ===")

			# 5) Update status WITHOUT save/validate (prevents “Missing fields” popups)
			frappe.db.set_value(self.doctype, self.name, "status", "Deployed", update_modified=False)

			# Send completion notification
			frappe.publish_realtime(
				event="frappe_site_update",
				message={
					"frappe_site": self.name,
					"status": "success",
					"message": "Deployment completed successfully",
				},
			)

			return {"status": 200, "message": "Deployment completed successfully"}

		except Exception as exc:
			# Log full traceback for operators
			frappe.log_error(frappe.get_traceback(), "frappe_site failed")

			# Stream error message
			error_msg = f"Deployment failed: {frappe.utils.cstr(exc)}"
			self.stream_deployment_update(f"ERROR: {error_msg}")

			# Send failure notification
			frappe.publish_realtime(
				event="frappe_site_update",
				message={
					"frappe_site": self.name,
					"status": "error",
					"message": error_msg,
				},
			)

			frappe.db.set_value(self.doctype, self.name, "status", "Failed", update_modified=False)
			return {"status": 500, "message": frappe.utils.cstr(exc)}
