import subprocess

import frappe
from frappe import _

from nano_press.utils.ansible_runner import AnsibleOps


@frappe.whitelist(allow_guest=True)
def ping_server(**kwargs):
	try:
		host = kwargs.get("host")
		user = kwargs.get("user")
		port = kwargs.get("port")

		if not host and not user and not port:
			frappe.throw(_("Missing required connection details: provide 'host', 'user', and 'port'"))

		runner = AnsibleOps()
		result = runner.run_ping(
			host=host,
			user=user,
			port=port,
		)
		raw_json = result.get("raw_json", {})
		message = (
			raw_json.get("plays", [{}])[0].get("tasks", [{}])[0].get("hosts", {}).get(host, {}).get("msg", "")
		)

		ok = bool(result.get("ok"))
		return {
			"status": "success" if ok else "error",
			"ok": ok,
			"message": message,
		}

	except Exception as e:
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=True)
def check_domain_resolves_to_ip(domain: str, expected_ip: str) -> dict:
	"""Check if domain resolves to given IP using dig."""
	try:
		result = subprocess.run(
			["dig", "+short", domain],
			capture_output=True,
			text=True,
			timeout=5,
		)

		if result.returncode != 0:
			return {
				"success": False,
				"resolved_ips": [],
				"message": f"dig command failed: {result.stderr.strip()}",
			}

		resolved_ips = [line.strip() for line in result.stdout.splitlines() if line.strip()]

		if not resolved_ips:
			return {"success": False, "resolved_ips": [], "message": f"No A/AAAA records found for {domain}"}

		if expected_ip in resolved_ips:
			return {
				"success": True,
				"resolved_ips": resolved_ips,
				"message": f"{domain} resolves to {expected_ip}",
			}

		return {
			"success": False,
			"resolved_ips": resolved_ips,
			"message": f"{domain} resolves to {resolved_ips}, not {expected_ip}",
		}

	except subprocess.TimeoutExpired:
		frappe.log_error(f"dig command timed out for domain: {domain}")
		return {"success": False, "resolved_ips": [], "message": "dig command timed out"}

	except Exception as e:
		frappe.log_error(f"Error occurred while checking domain {domain}: {e}")
		return {"success": False, "resolved_ips": [], "message": f"Error: {e}"}


@frappe.whitelist()
def register_custom_app(
	app_name: str, github_url: str, branch: str, token: str | None = None, order: int | None = None
) -> dict:
	try:
		if not app_name or not github_url or not branch:
			frappe.throw(_("app_name, github_url, and branch are required"))

		app_name_normalized = app_name.lower().strip()

		if frappe.db.exists("Apps", app_name_normalized):
			app_doc = frappe.get_doc("Apps", app_name_normalized)
			app_doc.repo_url = github_url
			app_doc.branch = branch
			if token:
				app_doc.pat_token = token
			if order is not None:
				app_doc.order = order
			app_doc.save(ignore_permissions=True)
		else:
			app_doc = frappe.get_doc(
				{
					"doctype": "Apps",
					"app_name": app_name_normalized,
					"repo_url": github_url,
					"branch": branch,
					"pat_token": token or "",
					"is_custom": 1,
					"enabled": 1,
					"order": order if order is not None else 999,
				}
			)
			app_doc.insert(ignore_permissions=True)

		frappe.db.commit()  # nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit

		return {
			"success": True,
			"app_reference_id": app_doc.name,
			"message": _("Custom app registered securely"),
		}

	except Exception as e:
		frappe.log_error(f"Error registering custom app: {e}")
		frappe.db.rollback()
		return {"success": False, "message": str(e)}


@frappe.whitelist()
def delete_custom_app(app_name: str) -> dict:
	try:
		if not app_name:
			frappe.throw(_("app_name is required"))

		app_name_normalized = app_name.lower().strip()

		if not frappe.db.exists("Apps", app_name_normalized):
			return {"success": True, "message": _("App not found or already deleted")}

		app_doc = frappe.get_doc("Apps", app_name_normalized)

		if not app_doc.is_custom:
			frappe.throw(_("Cannot delete non-custom apps"))

		frappe.delete_doc("Apps", app_name_normalized, ignore_permissions=True)
		frappe.db.commit()  # nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit

		return {"success": True, "message": _("Custom app deleted successfully")}

	except Exception as e:
		frappe.log_error(f"Error deleting custom app: {e}")
		frappe.db.rollback()
		return {"success": False, "message": str(e)}


@frappe.whitelist()
def initiate_site_deployment(
	server_name: str, apps: list, custom_apps: list, frappe_version: str, domain: str | None = None
) -> dict:
	try:
		from nano_press.nano_press.doctype.custom_image.custom_image import create_and_build_custom_image

		apps = frappe.parse_json(apps) if isinstance(apps, str) else apps
		custom_apps = frappe.parse_json(custom_apps) if isinstance(custom_apps, str) else (custom_apps or [])

		if not frappe.db.exists("Server", server_name):
			frappe.throw(_("Server '{0}' not found").format(server_name))

		import time

		timestamp = int(time.time())
		image_name = f"custom-{timestamp}"

		custom_image_result = create_and_build_custom_image(
			server_name=server_name,
			apps=apps,
			custom_apps=custom_apps,
			image_name=image_name,
			frappe_version=frappe_version,
		)

		custom_image_name = custom_image_result.get("custom_image_name")
		if not custom_image_name:
			raise Exception("Failed to create custom image")

		import time

		max_wait = 1200
		elapsed = 0
		interval = 10

		while elapsed < max_wait:
			custom_image = frappe.get_doc("Custom Image", custom_image_name)

			if custom_image.build_status == "Built":
				break
			elif custom_image.build_status == "Failed":
				raise Exception("Custom image build failed")

			frappe.db.commit()  # nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit
			time.sleep(interval)
			elapsed += interval

		if elapsed >= max_wait:
			raise Exception("Custom image build timed out")

		site_doc = frappe.new_doc("Frappe Site")
		site_doc.update(
			{
				"server_name": server_name,
				"site_url": domain.strip() if domain else None,
				"custom_image": custom_image_name,
				"is_custom": 1,
				"status": "Deploying",
			}
		)

		for app_name in apps:
			site_doc.append("install_apps", {"app_name": app_name})

		site_doc.insert(ignore_permissions=True)
		site_doc.submit()

		site_doc.enqueue_full_deployment()

		return {
			"success": True,
			"site_name": site_doc.name,
			"site_url": site_doc.site_url,
			"custom_image_name": custom_image_name,
			"message": _("Deployment started"),
		}

	except Exception as e:
		frappe.log_error(f"Error starting deployment: {e}")
		frappe.db.rollback()
		return {"success": False, "message": str(e)}


@frappe.whitelist()
def get_deployment_status(site_name: str) -> dict:
	try:
		if not frappe.db.exists("Frappe Site", site_name):
			return {"error": "Site not found"}

		doc = frappe.get_doc("Frappe Site", site_name)

		return {
			"status": doc.status,
			"substep": doc.deployment_substep,
			"site_url": doc.site_url,
			"is_complete": doc.status == "Deployed",
			"is_failed": doc.status == "Failed",
		}

	except Exception as e:
		frappe.log_error(f"Error getting deployment status: {e}")
		return {"error": str(e)}
