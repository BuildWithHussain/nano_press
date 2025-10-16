# Copyright (c) 2025, Venkatesh M and contributors
# For license information, please see license.txt

import base64
import json
from typing import Any

import frappe
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

		# Process each app in the configuration
		for app_item in self.apps_config:
			if not app_item.app_name:
				continue

			# Get the linked Apps document
			try:
				app_doc = frappe.get_doc("Apps", app_item.app_name)
			except frappe.DoesNotExistError:
				frappe.throw(f"App '{app_item.app_name}' not found in Apps doctype")

			# Validate required fields
			if not app_doc.repo_url or not app_doc.branch:
				frappe.throw(
					f"App '{app_item.app_name}' has incomplete configuration (missing repo_url or branch)"
				)

			# Build app configuration
			app_config = {"url": self._build_repo_url(app_doc), "branch": app_doc.branch}

			apps_list.append(app_config)

		# Sort by order if specified
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

		# Handle private repositories with PAT tokens
		if app_doc.is_private and app_doc.pat_token:
			# Convert https://github.com/owner/repo.git to https://PAT@github.com/owner/repo.git
			if repo_url.startswith("https://"):
				# Extract domain and path
				url_parts = repo_url.replace("https://", "").split("/", 1)
				if len(url_parts) == 2:
					domain = url_parts[0]
					path = url_parts[1]
					return f"https://{app_doc.pat_token}@{domain}/{path}"

			# For other formats, user should provide correct URL format
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
		# Create mapping of app_name to order
		app_order_map = {}
		for app_item in self.apps_config:
			if app_item.app_name:
				try:
					app_doc = frappe.get_doc("Apps", app_item.app_name)
					app_order_map[app_item.app_name] = (
						app_doc.order or 999
					)  # Default high order for unspecified
				except frappe.DoesNotExistError:
					app_order_map[app_item.app_name] = 999

		# Sort apps_list by the order from Apps doctype
		app_names = [app_item.app_name for app_item in self.apps_config if app_item.app_name]

		# Create list of (app_config, order) tuples
		apps_with_order = []
		for i, app_config in enumerate(apps_list):
			app_name = app_names[i] if i < len(app_names) else None
			order = app_order_map.get(app_name, 999)
			apps_with_order.append((app_config, order))

		# Sort by order and return just the app configs
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
			vars = self.get_deployment_vars()
			result = run_playbook(
				server_name=self.server_name, playbook_path="build_custom_image.yml", extra_vars=vars
			)

			if result.get("status") != "success":
				self.db_set("build_status", "Failed")
				self._send_build_notification("error", result.get("message", "Unknown error"))
				self._send_email_notification("error")
				raise Exception(f"Build failed: {result.get('message', 'Unknown error')}")

			self.db_set("build_status", "Built")
			self._send_build_notification("success", "Image built successfully")
			self._send_email_notification("success")

		except Exception as e:
			frappe.log_error(str(e), "Image Build Failed")
			raise

	@frappe.whitelist()
	def enqueue_build_custom_image(self):
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
			# Send real-time notification to user
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

			# Also send system notification
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

			# Send email to document owner
			frappe.sendmail(
				recipients=[self.owner],
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
