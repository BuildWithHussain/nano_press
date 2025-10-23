import subprocess

import frappe
from frappe.utils.user import is_website_user

__version__ = "0.0.1"


def has_app_permission():
	if frappe.session.user == "Administrator":
		return True

	if is_website_user():
		return False

	return True


def add_user_role(doc, event=None):
	doc.add_roles("Nano Press User")


@frappe.whitelist()
def get_admin_password(site_name):
	site = frappe.get_doc("Frappe Site", site_name)
	return site.get_password("admin_password")


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
