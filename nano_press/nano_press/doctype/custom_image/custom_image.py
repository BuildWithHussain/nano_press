# Copyright (c) 2025, Venkatesh M and contributors
# For license information, please see license.txt

import base64
import json

import frappe
from frappe import _
from frappe.model.document import Document

from nano_press.utils.ansible_runner import run_playbook


class CustomImage(Document):
	def before_save(self):
		self.apps_json_base64 = self._generate_apps_json_base64()
		self._set_image_tag()

	def _set_image_tag(self):
		clean_name = self.image_name.lower().replace(" ", "-")
		self.image_tag = f"{clean_name}:latest"

	def _generate_apps_json(self):
		if not self.apps_config:
			frappe.throw(_("No apps configured for this Custom Image"))

		apps_list = []
		for app_item in self.apps_config:
			if not app_item.app_name:
				continue

			app_doc = frappe.get_cached_doc("Apps", app_item.app_name)
			if not app_doc.repo_url or not app_doc.branch:
				frappe.throw(
					_("App '{0}' has incomplete configuration (missing repo_url or branch)").format(
						app_item.app_name
					)
				)

			apps_list.append(
				{
					"url": self._build_repo_url(app_doc),
					"branch": app_doc.branch,
				}
			)

		return json.dumps(self._sort_apps_by_order(apps_list), indent=2)

	def _generate_apps_json_base64(self):
		apps_json = self._generate_apps_json()
		return base64.b64encode(apps_json.encode("utf-8")).decode("utf-8")

	def _build_repo_url(self, app_doc):
		repo_url = (app_doc.repo_url or "").strip()

		if not app_doc.is_public and app_doc.pat_token and repo_url.startswith("https://"):
			url_parts = repo_url.replace("https://", "").split("/", 1)
			if len(url_parts) == 2:
				return f"https://{app_doc.pat_token}@{url_parts[0]}/{url_parts[1]}"

		return repo_url

	def _sort_apps_by_order(self, apps_list):
		app_names = [item.app_name for item in self.apps_config if item.app_name]
		app_orders = {name: frappe.db.get_value("Apps", name, "order") or 999 for name in app_names}

		apps_with_order = [
			(app, app_orders.get(app_names[i], 999)) for i, app in enumerate(apps_list) if i < len(app_names)
		]
		return [app for app, _ in sorted(apps_with_order, key=lambda x: x[1])]

	def _get_deployment_vars(self):
		return {
			"image_name": self.image_name,
			"frappe_version": self.frappe_version,
			"apps_json_base64": self._generate_apps_json_base64(),
		}

	def build_custom_image(self):
		start_time = frappe.utils.now_datetime()
		self._update_status("Building")

		try:
			result = run_playbook(
				server_name=self.server_name,
				playbook_path="build_custom_image.yml",
				extra_vars=self._get_deployment_vars(),
			)

			if result.get("status") != "success":
				self._on_build_failure(result.get("message", "Unknown error"))
				return

			self._on_build_success(start_time)

		except Exception:
			frappe.db.rollback()
			self._update_status("Failed")
			frappe.log_error(title=_("Custom Image Build Failed"))
			raise

	def _update_status(self, status):
		frappe.db.set_value("Custom Image", self.name, "build_status", status, update_modified=False)
		frappe.db.commit()

	def _on_build_success(self, start_time):
		end_time = frappe.utils.now_datetime()
		duration = int((end_time - start_time).total_seconds())
		frappe.db.set_value(
			"Custom Image",
			self.name,
			{
				"build_status": "Built",
				"built_at": end_time,
				"build_duration": duration,
			},
		)
		self.reload()
		self._notify("success", _("Image built successfully"))

	def _on_build_failure(self, error_message):
		self._update_status("Failed")
		self._notify("error", error_message)
		frappe.log_error(message=error_message, title=_("Custom Image Build Failed"))

	def _notify(self, status, message):
		self._send_realtime_notification(status, message)
		self._send_email_notification(status)

	def _send_realtime_notification(self, status, message):
		try:
			frappe.publish_realtime(
				event="custom_image_build_update",
				message={
					"custom_image": self.name,
					"status": status,
					"message": message,
				},
				user=self.owner,
			)

			frappe.get_doc(
				{
					"doctype": "Notification Log",
					"subject": _("Custom Image Build: {0}").format(self.image_name),
					"email_content": message,
					"for_user": self.owner,
					"type": "Alert",
					"document_type": "Custom Image",
					"document_name": self.name,
				}
			).insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(title=_("Build Notification Failed"))

	def _send_email_notification(self, status):
		try:
			recipient = frappe.db.get_value("User", self.owner, "email")
			if not recipient or "@" not in recipient:
				return

			if status == "success":
				subject = _("Custom Image Build Successful - {0}").format(self.image_name)
				message = f"""
				<p>Your custom Docker image <strong>{self.image_name}</strong> has been built successfully.</p>
				<p><strong>Image Tag:</strong> {self.image_tag}</p>
				<p><strong>Server:</strong> {self.server_name}</p>
				<p><strong>Frappe Version:</strong> {self.frappe_version}</p>
				<p><strong>Build Duration:</strong> {self.build_duration or 0} seconds</p>
				"""
			else:
				subject = _("Custom Image Build Failed - {0}").format(self.image_name)
				message = f"""
				<p>Your custom Docker image build encountered an error.</p>
				<p><strong>Image Name:</strong> {self.image_name}</p>
				<p><strong>Server:</strong> {self.server_name}</p>
				<p>Please check the build log for more details.</p>
				"""

			frappe.sendmail(
				recipients=[recipient],
				subject=subject,
				message=message,
				reference_doctype="Custom Image",
				reference_name=self.name,
			)
		except Exception:
			frappe.log_error(title=_("Email Notification Failed"))

	@frappe.whitelist()
	def enqueue_build_custom_image(self):
		frappe.enqueue_doc(
			"Custom Image",
			self.name,
			"build_custom_image",
			queue="long",
			timeout=1200,
			enqueue_after_commit=True,
		)
		return {"status": "queued", "message": _("Build process has been queued")}

	@frappe.whitelist()
	def preview_apps_json_for_form(self):
		try:
			apps_json = self._generate_apps_json()
			return {
				"success": True,
				"apps_json": apps_json,
				"apps_json_base64": base64.b64encode(apps_json.encode()).decode(),
				"app_count": len(json.loads(apps_json)),
			}
		except Exception as e:
			return {"success": False, "error": str(e)}


@frappe.whitelist()
def create_and_build_custom_image(server_name, apps, custom_apps, image_name, frappe_version):
	apps = frappe.parse_json(apps) if isinstance(apps, str) else apps
	custom_apps = frappe.parse_json(custom_apps) if isinstance(custom_apps, str) else (custom_apps or [])

	server = frappe.get_doc("Server", server_name)
	if server.verify_status != "Prepared":
		frappe.throw(_("Server must be in 'Prepared' status before building custom images"))

	custom_image = frappe.new_doc("Custom Image")
	custom_image.update(
		{
			"server_name": server_name,
			"image_name": image_name,
			"frappe_version": frappe_version,
			"build_status": "Draft",
		}
	)

	for app_name in apps:
		app_doc_name = frappe.db.get_value("Apps", {"scrubbed_name": app_name.lower()}, "name")
		if app_doc_name:
			custom_image.append("apps_config", {"app_name": app_doc_name})

	for custom_app in custom_apps:
		app_name = custom_app.get("name")
		if not app_name:
			continue

		if not frappe.db.exists("Apps", app_name):
			frappe.get_doc(
				{
					"doctype": "Apps",
					"app_name": app_name,
					"repo_url": custom_app.get("githubUrl", ""),
					"branch": custom_app.get("branch", "main"),
					"pat_token": custom_app.get("token", ""),
					"is_custom": 1,
					"enabled": 1,
					"order": 999,
				}
			).insert(ignore_permissions=True)

		custom_image.append("apps_config", {"app_name": app_name})

	custom_image.insert(ignore_permissions=True)
	result = custom_image.enqueue_build_custom_image()

	return {
		"status": "success",
		"message": result.get("message"),
		"custom_image_name": custom_image.name,
	}


@frappe.whitelist()
def get_build_status(custom_image_name):
	doc = frappe.get_doc("Custom Image", custom_image_name)
	return {
		"status": doc.build_status,
		"build_duration": doc.build_duration or 0,
		"built_at": doc.built_at,
		"image_tag": doc.image_tag if doc.build_status == "Built" else None,
	}
