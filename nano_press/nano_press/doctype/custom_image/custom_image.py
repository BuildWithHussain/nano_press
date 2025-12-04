# Copyright (c) 2025, Venkatesh M and contributors
# For license information, please see license.txt

import base64
import json
from typing import Any

import frappe
from frappe import _
from frappe.model.document import Document

from nano_press.utils.ansible_runner import run_playbook


class CustomImage(Document):
	def before_save(self):
		self.apps_json_base64 = self.generate_apps_json_base64()
		self.set_image_tag()

	def generate_apps_json(self) -> str:
		"""Generate apps.json content from this Custom Image's apps configuration.

		Returns:
			JSON string in frappe_docker apps.json format

		Raises:
			frappe.ValidationError: If invalid app configuration found
		"""
		if not self.apps_config:
			frappe.throw("No apps configured for this Custom Image")

		apps_list = []

		for app_item in self.apps_config:
			if not app_item.app_name:
				continue

			try:
				app_doc = frappe.get_doc("Apps", app_item.app_name)
			except frappe.DoesNotExistError:
				frappe.throw(f"App '{app_item.app_name}' not found in Apps doctype")

			if not app_doc.repo_url or not app_doc.branch:
				frappe.throw(
					f"App '{app_item.app_name}' has incomplete configuration (missing repo_url or branch)"
				)

			app_config = {"url": self._build_repo_url(app_doc), "branch": app_doc.branch}

			apps_list.append(app_config)

		sorted_apps = self._sort_apps_by_order(apps_list)

		return json.dumps(sorted_apps, indent=2)

	def set_image_tag(self) -> str:
		"""Generate image tag using just the image name."""
		clean_name = self.image_name.lower().replace(" ", "-")
		self.image_tag = f"{clean_name}:latest"

	def generate_apps_json_base64(self) -> str:
		"""Generate base64 encoded apps.json for docker build args.

		Returns:
			Base64 encoded JSON string ready for APPS_JSON_BASE64 env var
		"""
		apps_json = self.generate_apps_json()
		return base64.b64encode(apps_json.encode("utf-8")).decode("utf-8")

	def get_deployment_vars(self) -> dict:
		"""Prepare all variables needed for Image Build"""

		return {
			"image_name": self.image_name,
			"frappe_version": self.frappe_version,
			"apps_json_base64": self.generate_apps_json_base64(),
		}

	def _build_repo_url(self, app_doc) -> str:
		"""Build repository URL with PAT token if private repo.

		Args:
			app_doc: Apps document

		Returns:
			Repository URL formatted for git clone
		"""
		repo_url = app_doc.repo_url.strip()

		if app_doc.is_private and app_doc.pat_token:
			# Convert https://github.com/owner/repo.git to https://PAT@github.com/owner/repo.git
			if repo_url.startswith("https://"):
				# Extract domain and path
				url_parts = repo_url.replace("https://", "").split("/", 1)
				if len(url_parts) == 2:
					domain = url_parts[0]
					path = url_parts[1]
					return f"https://{app_doc.pat_token}@{domain}/{path}"

			frappe.msgprint(
				f"Warning: Private repo URL format might need manual adjustment for {app_doc.app_name}"
			)

		return repo_url

	def _sort_apps_by_order(self, apps_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
		"""Sort apps by order field from Apps doctype.

		Args:
			apps_list: Generated apps configuration list

		Returns:
			Sorted apps list by order priority
		"""
		app_order_map = {}
		for app_item in self.apps_config:
			if app_item.app_name:
				try:
					app_doc = frappe.get_doc("Apps", app_item.app_name)
					app_order_map[app_item.app_name] = app_doc.order or 999
				except frappe.DoesNotExistError:
					app_order_map[app_item.app_name] = 999

		app_names = [app_item.app_name for app_item in self.apps_config if app_item.app_name]

		apps_with_order = []
		for i, app_config in enumerate(apps_list):
			app_name = app_names[i] if i < len(app_names) else None
			order = app_order_map.get(app_name, 999)
			apps_with_order.append((app_config, order))

		sorted_apps_with_order = sorted(apps_with_order, key=lambda x: x[1])
		return [app_config for app_config, _ in sorted_apps_with_order]

	@frappe.whitelist()
	def preview_apps_json_for_form(self) -> dict[str, Any]:
		"""Generate apps.json preview for display in the form.

		Returns:
			Dict with formatted apps.json and metadata for UI display
		"""
		try:
			apps_json = self.generate_apps_json()
			apps_json_base64 = self.generate_apps_json_base64()
			parsed_apps = json.loads(apps_json)

			return {
				"success": True,
				"apps_json": apps_json,
				"apps_json_base64": apps_json_base64,
				"app_count": len(parsed_apps),
				"apps_summary": [
					{
						"name": app.get("url", "").split("/")[-1].replace(".git", ""),
						"url": app.get("url", ""),
						"branch": app.get("branch", ""),
					}
					for app in parsed_apps
				],
			}
		except Exception as e:
			return {
				"success": False,
				"error": str(e),
				"apps_json": "",
				"apps_json_base64": "",
				"app_count": 0,
				"apps_summary": [],
			}

	def build_custom_image(self):
		try:
			self.db_set("build_status", "Building")
			frappe.db.commit()

			vars = self.get_deployment_vars()
			result = run_playbook(
				server_name=self.server_name, playbook_path="build_custom_image.yml", extra_vars=vars
			)

			if result.get("status") != "success":
				self.db_set("build_status", "Failed")
				self._send_build_notification("error", result.get("message", "Unknown error"))
				self._send_email_notification("error")
				frappe.log_error(result.get("message"), _("Custom Image Build Failed"))
				raise Exception(f"Build failed: {result.get('message', 'Unknown error')}")

			self.db_set("build_status", "Built")
			self._send_build_notification("success", "Image built successfully")
			self._send_email_notification("success")
			self.built_at = frappe.utils.now_datetime()
			self.build_duration = (self.built_at - self.creation).total_seconds()
			self.save()
			frappe.db.commit()

		except Exception as e:
			frappe.log_error(str(e), "Image Build Failed")
			self.db_set("build_status", "Failed")
			frappe.db.commit()
			raise

	@frappe.whitelist()
	def enqueue_build_custom_image(self):
		"""Enqueue the build process for this Custom Image."""
		frappe.enqueue_doc(
			"Custom Image",
			self.name,
			"build_custom_image",
			queue="long",
			timeout=60 * 20,
			enqueue_after_commit=True,
		)
		return {"status": "queued", "message": f"Build process for {self.name} has been queued."}

	def _send_build_notification(self, status: str, message: str):
		"""Send real-time notification about build status.

		Args:
			status: 'success' or 'error'
			message: Notification message
		"""
		try:
			frappe.publish_realtime(
				event="custom_image_build_update",
				message={
					"custom_image": self.name,
					"status": status,
					"message": message,
					"build_status": self.build_status,
					"timestamp": frappe.utils.now_datetime(),
				},
				user=frappe.session.user,
			)

			frappe.get_doc(
				{
					"doctype": "Notification Log",
					"subject": f"Custom Image Build: {self.image_name}",
					"email_content": message,
					"for_user": frappe.session.user,
					"type": "Alert",
					"document_type": "Custom Image",
					"document_name": self.name,
				}
			).insert(ignore_permissions=True)

		except Exception as e:
			frappe.log_error(f"Failed to send build notification: {e!s}", "Build Notification")

	def _send_email_notification(self, status: str):
		"""Send email notification directly using Frappe's email system.

		Args:
			status: 'success' or 'error'
		"""
		try:
			recipient = frappe.db.get_value("User", self.owner, "email") or frappe.session.user
			if not recipient or "@" not in recipient:
				frappe.log_error(f"Invalid email for user {self.owner}", "Email Notification")
				return
			if status == "success":
				subject = f"🚀 Custom Image Build Successful - {self.image_name}"
				message = f"""
				<h2>🚀 Custom Image Build Successful</h2>
				<p>Your custom Docker image <strong>{self.image_name}</strong> has been built successfully!</p>

				<p><strong>Image Tag:</strong> <code>{self.image_tag}</code></p>
				<p><strong>Build Duration:</strong> {self.build_duration} seconds</p>
				<p><strong>Server:</strong> {self.server_name}</p>
				<p><strong>Frappe Version:</strong> {self.frappe_version}</p>

				<p>Your custom image is now ready to use in deployments!</p>
				"""
			else:
				subject = f"❌ Custom Image Build Failed - {self.image_name}"
				message = f"""
				<h2>⚠️ Custom Image Build Failed</h2>
				<p>Unfortunately, your custom Docker image build encountered an error.</p>

				<p><strong>Image Name:</strong> {self.image_name}</p>
				<p><strong>Server:</strong> {self.server_name}</p>
				<p><strong>Build Duration:</strong> {self.build_duration} seconds</p>

				<p>Please check the build log for more details.</p>
				"""

			frappe.sendmail(
				recipients=[recipient],
				subject=subject,
				message=message,
				reference_doctype="Custom Image",
				reference_name=self.name,
			)

		except Exception as e:
			frappe.log_error(f"Failed to send email notification: {e!s}", "Email Notification")


@frappe.whitelist()
def preview_apps_json(custom_image_name: str) -> dict[str, Any]:
	"""API endpoint to preview generated apps.json for a Custom Image.

	Args:
		custom_image_name: Name of the Custom Image document

	Returns:
		Dict with apps_json content and base64 version
	"""
	try:
		custom_image = frappe.get_doc("Custom Image", custom_image_name)
		apps_json = custom_image.generate_apps_json()
		apps_json_base64 = custom_image.generate_apps_json_base64()

		return {
			"success": True,
			"apps_json": apps_json,
			"apps_json_base64": apps_json_base64,
			"app_count": len(json.loads(apps_json)),
		}
	except Exception as e:
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def create_and_build_custom_image(server_name, apps, custom_apps, image_name, frappe_version):
	try:
		if isinstance(apps, str):
			apps = json.loads(apps)
		if isinstance(custom_apps, str):
			custom_apps = json.loads(custom_apps) if custom_apps else []
		if custom_apps is None:
			custom_apps = []

		if not frappe.db.exists("Server", server_name):
			frappe.throw(_("Server {0} not found").format(server_name))

		server = frappe.get_doc("Server", server_name)
		if server.verify_status != "Prepared":
			frappe.throw(_("Server must be in 'Prepared' status before building custom images"))

		custom_image = frappe.get_doc(
			{
				"doctype": "Custom Image",
				"server_name": server_name,
				"image_name": image_name,
				"frappe_version": frappe_version.lower(),
				"build_status": "Draft",
			}
		)

		for app_name in apps:
			app_filters = [["scrubbed_name", "=", app_name.lower()]]
			apps_docs = frappe.get_all("Apps", filters=app_filters, fields=["name"])

			if apps_docs:
				custom_image.append("apps_config", {"app_name": apps_docs[0].name})
			else:
				frappe.log_error(f"App with scrubbed_name '{app_name}' not found in Apps doctype")

		for custom_app in custom_apps:
			app_name = custom_app.get("name", "")
			if not app_name:
				continue

			if not frappe.db.exists("Apps", app_name):
				apps_doc = frappe.get_doc(
					{
						"doctype": "Apps",
						"name": app_name,
						"scrubbed_name": app_name.lower(),
						"repo_url": custom_app.get("githubUrl", ""),
						"branch": custom_app.get("branch", "main"),
						"personal_access_token": custom_app.get("token", ""),
						"is_custom": 1,
						"order": 999,
					}
				)
				apps_doc.insert(ignore_permissions=True)

			custom_image.append("apps_config", {"app_name": app_name})

		custom_image.insert(ignore_permissions=True)

		result = custom_image.enqueue_build_custom_image()

		return {
			"status": "success",
			"message": result.get("message", "Build process queued successfully"),
			"custom_image_name": custom_image.name,
		}

	except Exception as e:
		frappe.log_error(f"Error creating custom image: {e}")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_build_status(custom_image_name):
	"""
	Get build status for a Custom Image.

	Args:
		custom_image_name: Name of the Custom Image doctype

	Returns:
		dict: {status, build_duration, built_at, build_log}
	"""
	try:
		if not frappe.db.exists("Custom Image", custom_image_name):
			frappe.throw(_("Custom Image {0} not found").format(custom_image_name))

		custom_image = frappe.get_doc("Custom Image", custom_image_name)

		return {
			"status": custom_image.build_status,
			"build_duration": custom_image.build_duration or 0,
			"built_at": custom_image.built_at,
			"build_log": custom_image.build_log if hasattr(custom_image, "build_log") else "",
			"image_tag": custom_image.image_tag if custom_image.build_status == "Built" else None,
		}

	except Exception as e:
		frappe.log_error(f"Error getting build status: {e}")
		return {"status": "error", "message": str(e)}
