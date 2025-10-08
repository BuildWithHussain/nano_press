# Copyright (c) 2025, Venkatesh M and contributors
# For license information, please see license.txt

import os

import frappe
from frappe.model.document import Document
from frappe.utils import random_string

from nano_press.nano_press.utils.ansible.src.AnsibleRunner import AnsibleRunner
from nano_press.utils.log import append_long_text


class FrappeSite(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from nano_press.nano_press.doctype.app_install_item.app_install_item import AppInstallItem

		admin_password: DF.Password
		amended_from: DF.Link | None
		custom_image: DF.Link | None
		db_password: DF.Password | None
		db_username: DF.Data | None
		deployment_log: DF.LongText | None
		docker_image: DF.Data | None
		install_apps: DF.Table[AppInstallItem]
		is_custom: DF.Check
		last_deployed_at: DF.Datetime | None
		server_name: DF.Link
		site_name: DF.Data
		ssl_enabled: DF.Check
		status: DF.Literal["Not Deployed", "Ready To Deploy", "Deploying", "Deployed", "Failed", "Stopped"]
		traefik_domain: DF.Data | None
		traefik_email: DF.Data | None
		traefik_password: DF.Password | None
		username: DF.Data | None
	# end: auto-generated types

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
			frappe.throw("Please select a Server before deploying.")
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

		if not self.db_password:
			self.db_password = random_string(10)

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
		if not self.ssl_enabled:
			traefik_password = ""
		else:
			traefik_password = self.get_password("traefik_password")

		docker_image = self.get_docker_image()
		return {
			"ssl_enabled": int(self.ssl_enabled or 0),
			"docker_image": docker_image,
			"site_name": self.site_name or "",
			"traefik_domain": self.traefik_domain or "",
			"traefik_email": self.traefik_email or "",
			"traefik_plain_password": traefik_password,
			"install_apps_csv": install_apps_csv,
			"admin_password": self.get_password("admin_password") or "admin",
		}

	def _playbooks_base(self) -> str:
		return frappe.get_app_path("nano_press", "nano_press", "utils", "ansible", "playbooks")

	def _run_playbook(
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
		append_long_text(
			self,
			"deployment_log",
			out,
			header_title=f"Playbook: {playbook_filename}",
			newest_on_top=True,
			trim_to_bytes=100000,
		)

	@frappe.whitelist()
	def prepare_for_deployment(self) -> dict:
		self.validate_server()
		vars = self.get_deployment_vars()
		self.db_set("status", "Deploying", update_modified=False)

		try:
			self._run_playbook("install_docker.yml")
			self._run_playbook("prepare_repo.yml")
			self._run_playbook("render_pwd.yml", extra_vars=vars)
			self.db_set("status", "Ready To Deploy", update_modified=False)
			self.db_set("last_deployed_at", frappe.utils.now_datetime(), update_modified=False)
			return {"status": 200, "message": "Deployment prepared successfully"}

		except Exception as exc:
			frappe.log_error(frappe.get_traceback(), "prepare_for_deployment failed")
			self.db_set("status", "Failed", update_modified=False)
			return {"status": 500, "message": frappe.utils.cstr(exc)}

	@frappe.whitelist()
	def deploy_site(self) -> dict:
		self.validate_server()
		try:
			self._run_playbook("compose_up.yml", timeout=60 * 20)
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
			self._run_playbook("stop_all_containers.yml", timeout=60 * 15)
			self.db_set("status", "Stopped", update_modified=False)

			return {"status": 200, "message": "All containers stopped successfully"}

		except Exception as exc:
			frappe.log_error(frappe.get_traceback(), "stop_all_containers failed")
			err = f"Stop failed: {frappe.utils.cstr(exc)}"
			self.append_log(err)
			self.db_set("status", "Failed", update_modified=False)
			return {"status": 500, "message": frappe.utils.cstr(exc)}
