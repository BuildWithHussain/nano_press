# Copyright (c) 2025, Venkatesh M and contributors
# For license information, please see license.txt

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import frappe

from nano_press.utils.ansible_runner import run_playbook


class RemoteImageBuilder:
	def __init__(self, custom_image_name: str):
		self.custom_image_name = custom_image_name
		self.custom_image_doc = frappe.get_doc("Custom Image", custom_image_name)
		self._validate_custom_image()

	def build_image_on_server(self, server_name: str | None = None) -> str:
		if not server_name:
			if not self.custom_image_doc.server_name:
				frappe.throw("No server linked to Custom Image and no server_name provided")
			server_name = self.custom_image_doc.server_name

		server_doc = frappe.get_doc("Server", server_name)
		self._validate_server(server_doc)

		apps_json_base64 = self.custom_image_doc.generate_apps_json_base64()

		image_tag = self._generate_image_tag()

		self._update_build_start(image_tag)

		try:
			output = self._execute_remote_build(
				server_doc=server_doc, apps_json_base64=apps_json_base64, image_tag=image_tag
			)

			self._update_build_success(output)
			return output

		except Exception as e:
			self._update_build_failure(str(e))
			raise

	def _validate_custom_image(self) -> None:
		if not self.custom_image_doc.apps_config:
			frappe.throw("No apps configured for this Custom Image")

		if not self.custom_image_doc.frappe_version:
			frappe.throw("Frappe version not specified")

		if not self.custom_image_doc.image_name:
			frappe.throw("Image name not specified")

		if not self.custom_image_doc.server_name:
			frappe.throw("No server linked to this Custom Image")

	def _validate_server(self, server_doc) -> None:
		if server_doc.verify_status != "Verified":
			frappe.throw(
				f"Server {server_doc.name} is not verified. Please verify server connectivity first."
			)

	def _generate_image_tag(self) -> str:
		clean_name = self.custom_image_doc.image_name.lower().replace(" ", "-")
		return f"{clean_name}:latest"

	def _update_build_start(self, image_tag: str) -> None:
		self.custom_image_doc.build_status = "Building"
		self.custom_image_doc.image_tag = image_tag
		self.custom_image_doc.build_log = f"Starting build at {frappe.utils.now_datetime()}\n"
		self.custom_image_doc.save(ignore_permissions=True)
		frappe.db.commit()

	def _update_build_success(self, output: str) -> None:
		self.custom_image_doc.build_status = "Built"
		self.custom_image_doc.built_at = frappe.utils.now_datetime()
		self.custom_image_doc.build_log += f"\n\n=== BUILD COMPLETED ===\n{output}"
		self.custom_image_doc.save(ignore_permissions=True)
		frappe.db.commit()

	def _update_build_failure(self, error: str) -> None:
		self.custom_image_doc.build_status = "Failed"
		self.custom_image_doc.build_log += f"\n\n=== BUILD FAILED ===\n{error}"
		self.custom_image_doc.save(ignore_permissions=True)
		frappe.db.commit()

	def _execute_remote_build(self, server_doc, apps_json_base64: str, image_tag: str) -> str:
		playbook_path = self._get_build_playbook_path()

		extra_vars = {
			"apps_json_base64": apps_json_base64,
			"frappe_version": self.custom_image_doc.frappe_version,
			"image_tag": image_tag,
			"custom_image_name": self.custom_image_name,
			"build_method": "quick",
		}

		output = self._run_playbook_with_streaming(
			server_doc=server_doc, playbook_path=playbook_path, extra_vars=extra_vars
		)

		return output

	def _run_playbook_with_streaming(self, server_doc, playbook_path: str, extra_vars: dict) -> str:
		inventory_content = f"""
[all]
{server_doc.server_ip} ansible_user={server_doc.ssh_user or "root"} ansible_port={int(server_doc.ssh_port or 22)}
""".strip()

		complete_output = ""

		with tempfile.TemporaryDirectory() as tmpdir:
			inventory_path = Path(tmpdir) / "inventory.ini"
			inventory_path.write_text(inventory_content, encoding="utf-8")

			cmd = ["ansible-playbook", "-i", str(inventory_path), playbook_path]

			for key, value in extra_vars.items():
				cmd.extend(["--extra-vars", f"{key}={value}"])

			process = subprocess.Popen(
				cmd,
				stdout=subprocess.PIPE,
				stderr=subprocess.STDOUT,
				text=True,
				bufsize=1,
				universal_newlines=True,
			)

			while True:
				output = process.stdout.readline()
				if output == "" and process.poll() is not None:
					break
				if output:
					line = output.strip()
					complete_output += output
					self._stream_build_update(line)

			return_code = process.wait()

			if return_code != 0:
				raise Exception(f"Ansible playbook failed with return code {return_code}")

		return complete_output

	def _stream_build_update(self, log_line: str):
		try:
			frappe.publish_realtime(
				event="custom_image_build_live_update",
				message={
					"custom_image": self.custom_image_name,
					"log_line": log_line,
					"timestamp": frappe.utils.now_datetime(),
				},
			)

			if hasattr(self, "_line_count"):
				self._line_count += 1
			else:
				self._line_count = 1

			should_update_doc = (
				self._line_count % 10 == 0
				or "TASK" in log_line
				or "Step" in log_line
				or "ERROR" in log_line
				or "FAILED" in log_line
				or "ok:" in log_line
				or "changed:" in log_line
			)

			if should_update_doc:
				frappe.db.sql(
					"""UPDATE `tabCustom Image`
					   SET build_log = CONCAT(COALESCE(build_log, ''), %s)
					   WHERE name = %s""",
					(log_line + "\n", self.custom_image_name),
				)
				frappe.db.commit()

		except Exception as e:
			frappe.log_error(f"Failed to stream build update: {e!s}", "Build Streaming")

	def _get_build_playbook_path(self) -> str:
		"""Get path to the build playbook."""
		app_path = frappe.get_app_path("nano_press")
		playbook_path = os.path.join(
			app_path, "nano_press", "utils", "ansible", "playbooks", "build_custom_image.yml"
		)

		if not os.path.exists(playbook_path):
			frappe.throw(f"Build playbook not found at {playbook_path}")

		return playbook_path


@frappe.whitelist()
def trigger_remote_build(custom_image_name: str, server_name: str | None = None) -> dict[str, Any]:
	try:
		custom_image_doc = frappe.get_doc("Custom Image", custom_image_name)

		if not server_name:
			if not custom_image_doc.server_name:
				return {
					"success": False,
					"error": "No server linked to Custom Image and no server_name provided",
				}
			server_name = custom_image_doc.server_name

		server_doc = frappe.get_doc("Server", server_name)
		if server_doc.verify_status != "Verified":
			return {
				"success": False,
				"error": f"Server {server_doc.name} is not verified. Please verify server connectivity first.",
			}
		custom_image_doc.build_status = "Building"
		custom_image_doc.build_log = (
			f"Build queued at {frappe.utils.now_datetime()}\nWaiting for background worker...\n"
		)
		custom_image_doc.save(ignore_permissions=True)
		frappe.db.commit()

		job = frappe.enqueue_doc(
			"Custom Image",
			custom_image_name,
			"build_image_background",
			queue="long",
			timeout=3600,
			server_name=server_name,
			is_async=True,
			job_name=f"build_image_{custom_image_name}",
		)

		return {
			"success": True,
			"message": "Build job started in background",
			"job_id": job.id if hasattr(job, "id") else "queued",
		}

	except Exception as e:
		frappe.log_error(f"Failed to queue remote build: {e!s}", "Remote Image Build Queue")
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def get_available_servers() -> list:
	servers = frappe.get_all(
		"Server",
		filters={"verify_status": "Verified"},
		fields=["name", "server_name", "server_ip", "ssh_user"],
	)
	return servers
