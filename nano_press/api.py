from asyncio import subprocess

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
