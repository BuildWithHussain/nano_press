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
