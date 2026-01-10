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
def get_wallet_balance():
	user = frappe.session.user
	from nano_press.utils.wallet_manager import get_user_balance

	return {"balance": get_user_balance(user), "user": user}


@frappe.whitelist()
def get_wallet_transactions(limit=20, offset=0):
	user = frappe.session.user
	transactions = frappe.get_all(
		"Wallet Transaction",
		filters={"user": user},
		fields=[
			"name",
			"transaction_type",
			"amount",
			"balance_after",
			"description",
			"transaction_date",
			"reference_doctype",
			"reference_name",
		],
		order_by="transaction_date desc",
		limit=limit,
		start=offset,
	)
	return transactions


@frappe.whitelist()
def create_recharge_order(amount):
	user = frappe.session.user
	amount = float(amount)

	from nano_press.nano_press.doctype.nano_press_pricing.nano_press_pricing import NanoPressPricing

	min_amount = NanoPressPricing.get_minimum_recharge()

	if amount < min_amount:
		frappe.throw(f"Minimum recharge amount is ${min_amount}")

	from nano_press.utils.razorpay_integration import create_wallet_recharge_order

	return create_wallet_recharge_order(user, amount)


@frappe.whitelist()
def get_razorpay_key():
	from nano_press.utils.razorpay_integration import get_razorpay_key_id

	return {"key_id": get_razorpay_key_id()}


@frappe.whitelist()
def get_deployment_pricing():
	from nano_press.nano_press.doctype.nano_press_pricing.nano_press_pricing import NanoPressPricing

	return {
		"deployment_cost": NanoPressPricing.get_site_deployment_cost(),
		"currency": NanoPressPricing.get_currency(),
		"minimum_recharge": NanoPressPricing.get_minimum_recharge(),
	}
