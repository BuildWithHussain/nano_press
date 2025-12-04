# Copyright (c) 2025, Venkatesh M and contributors
# For license information, please see license.txt

import os

import frappe
from frappe.model.document import Document
from frappe.utils import random_string

from nano_press.utils.ansible_runner import run_playbook


class FrappeSite(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from nano_press.nano_press.doctype.app_install_item.app_install_item import AppInstallItem

		admin_password: DF.Password
		amended_from: DF.Link | None
		bench_name: DF.Data
		custom_image: DF.Link | None
		db_password: DF.Password | None
		db_username: DF.Data | None
		docker_image: DF.Data | None
		install_apps: DF.Table[AppInstallItem]
		is_custom: DF.Check
		is_development: DF.Check
		last_deployed_at: DF.Datetime | None
		port: DF.Int
		server_name: DF.Link
		site_url: DF.Data | None
		ssl_enabled: DF.Check
		status: DF.Literal["Not Deployed", "Ready To Deploy", "Deploying", "Deployed", "Failed", "Stopped"]
		username: DF.Data | None
	# end: auto-generated types

	def before_insert(self):
		self._ensure_password()

	def after_insert(self):
		# Set bench_name if not provided
		bench_name = self.bench_name or self.name
		self.db_set("bench_name", bench_name, update_modified=False)

		# Set site_url if not provided
		if not self.site_url:
			site_url = self._generate_site_url(bench_name)
			self.db_set("site_url", site_url, update_modified=False)

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
		if getattr(server, "verify_status", "Not Verified") != "Prepared":
			frappe.throw("Server is not verified. Please verify the server first.")
		return server

	def _ensure_password(self):
		if not self.admin_password:
			self.admin_password = random_string(10)

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

		# Get scrubbed_name from linked Apps documents
		install_apps = []
		for row in self.get("install_apps"):
			if row.app_name:
				app_doc = frappe.get_doc("Apps", row.app_name)
				if app_doc.scrubbed_name:
					install_apps.append(app_doc.scrubbed_name)

		install_apps_csv = ",".join(install_apps) if install_apps else "erpnext"

		docker_image = self.get_docker_image()
		return {
			"ssl_enabled": int(self.ssl_enabled or 0),
			"docker_image": docker_image,
			"site_url": self.site_url or "",
			"install_apps_csv": install_apps_csv,
			"admin_password": self.get_password("admin_password") or "admin",
			"db_username": self.db_username or "root",
			"db_password": self.get_password("db_password") or "admin",
			"bench_name": self.bench_name or "",
		}

	def _generate_site_url(self, bench_name: str) -> str:
		"""Generate a traefik.me domain for the site based on bench name and server IP.

		Args:
			bench_name: The bench name to use for the URL prefix

		Returns:
			str: Generated site URL in format: {bench_name}.{server_ip}.traefik.me
		"""
		server = frappe.get_doc("Server", self.server_name)
		site_prefix = bench_name.lower()
		return f"{site_prefix}.{server.server_ip}.traefik.me"

	@frappe.whitelist()
	def prepare_for_deployment(self) -> dict:
		self.validate_server()
		vars = self.get_deployment_vars()
		self.db_set("status", "Deploying", update_modified=False)

		try:
			result1 = run_playbook(
				server_name=self.server_name,
				playbook_path="prepare_repo.yml",
				extra_vars={"bench_name": self.bench_name},
			)
			if result1.get("status") != "success":
				raise Exception(f"prepare_repo.yml failed: {result1.get('message', 'Unknown error')}")

			result2 = run_playbook(
				server_name=self.server_name, playbook_path="render_pwd.yml", extra_vars=vars
			)
			if result2.get("status") != "success":
				raise Exception(f"render_pwd.yml failed: {result2.get('message', 'Unknown error')}")

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
			result = run_playbook(
				server_name=self.server_name,
				playbook_path="compose_up.yml",
				extra_vars={"bench_name": self.bench_name},
			)
			if result.get("status") != "success":
				raise Exception(f"compose_up.yml failed: {result.get('message', 'Unknown error')}")

			self.db_set("status", "Deployed", update_modified=False)
			return {"status": 200, "message": "Deployment completed successfully"}

		except Exception as exc:
			frappe.log_error(frappe.get_traceback(), "prepare_for_deployment failed")
			self.db_set("status", "Failed", update_modified=False)
			return {"status": 500, "message": frappe.utils.cstr(exc)}

	@frappe.whitelist()
	def stop_site(self) -> dict:
		try:
			result = run_playbook(
				server_name=self.server_name,
				playbook_path="stop_all_containers.yml",
				timeout=60 * 15,
				extra_vars={"bench_name": self.bench_name},
			)
			if result.get("status") != "success":
				raise Exception(f"compose_up.yml failed: {result.get('message', 'Unknown error')}")
			self.db_set("status", "Stopped", update_modified=False)

			return {"status": 200, "message": "All containers stopped successfully"}

		except Exception as exc:
			frappe.log_error(frappe.get_traceback(), "stop_all_containers failed")
			self.db_set("status", "Failed", update_modified=False)
			return {"status": 500, "message": frappe.utils.cstr(exc)}

	@frappe.whitelist()
	def remove_site(self) -> dict:
		try:
			result = run_playbook(
				server_name=self.server_name,
				playbook_path="destroy_site.yml",
				timeout=60 * 15,
				extra_vars={"bench_name": self.bench_name},
			)
			if result.get("status") != "success":
				raise Exception(f"destroy_site.yml failed: {result.get('message', 'Unknown error')}")
			self.db_set("status", "Stopped", update_modified=False)

			return {"status": 200, "message": "Site Destroyed successfully"}

		except Exception as exc:
			frappe.log_error(frappe.get_traceback(), "destroy_site.yml failed")
			self.db_set("status", "Failed", update_modified=False)
			return {"status": 500, "message": frappe.utils.cstr(exc)}

	@frappe.whitelist()
	def restart_site(self) -> dict:
		try:
			result = run_playbook(
				server_name=self.server_name,
				playbook_path="restart_site.yml",
				timeout=60 * 15,
				extra_vars={"bench_name": self.bench_name},
			)
			if result.get("status") != "success":
				raise Exception(f"restart_site.yml failed: {result.get('message', 'Unknown error')}")
			self.db_set("status", "Stopped", update_modified=False)

			return {"status": 200, "message": "Site Restarted successfully"}

		except Exception as exc:
			frappe.log_error(frappe.get_traceback(), "restart_site.yml failed")
			self.db_set("status", "Failed", update_modified=False)
			return {"status": 500, "message": frappe.utils.cstr(exc)}


@frappe.whitelist()
def prepare_for_deployment(site_name: str) -> dict:
	"""Wrapper function to call prepare_for_deployment on a Frappe Site document"""
	doc = frappe.get_doc("Frappe Site", site_name)
	return doc.prepare_for_deployment()


@frappe.whitelist()
def get_site_credentials(site_name: str) -> dict:
	"""Get the username and password for a Frappe Site.

	Args:
		site_name: Name of the Frappe Site document

	Returns:
		dict: {username, password}
	"""
	try:
		if not frappe.db.exists("Frappe Site", site_name):
			frappe.throw(f"Frappe Site {site_name} not found")

		doc = frappe.get_doc("Frappe Site", site_name)

		return {
			"username": doc.username or "Administrator",
			"password": doc.get_password("admin_password") or "",
		}

	except Exception as e:
		frappe.log_error(f"Error getting site credentials: {e}")
		return {"username": "", "password": ""}


@frappe.whitelist()
def deploy_site(site_name: str) -> dict:
	"""Wrapper function to call deploy_site on a Frappe Site document"""
	doc = frappe.get_doc("Frappe Site", site_name)
	return doc.deploy_site()
