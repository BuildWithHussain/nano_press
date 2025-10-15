import json

import frappe

from nano_press.nano_press.doctype.ansible_log.ansible_log import log_ansible_result
from nano_press.nano_press.utils.ansible.src.AnsibleRunner import AnsibleOps


@frappe.whitelist()
def run_playbook(**kwargs):
	"""
	Run an Ansible playbook on a server and log the result.

	Accepted args (one of host or server_name is required):
	  - host / server_ip:    IP or DNS of the server
	  - server_name:         name of the Server doctype record

	Optional (class can auto-resolve from Server doctype if omitted):
	  - user, port, private_key

	Playbook:
	  - playbook_path: absolute path OR short name like "prepare" / "prepare.yml"
	  - extra_vars: dict (JSON)
	  - become: bool
	  - become_user: str
	  - timeout: int (seconds)
	"""
	try:
		host = kwargs.get("host") or kwargs.get("server_ip")
		server_name = kwargs.get("server_name")

		playbook_arg = kwargs.get("playbook_path")
		if not playbook_arg:
			frappe.throw("Missing required field: playbook_path")

		extra_vars = kwargs.get("extra_vars", {}) or {}
		become = bool(kwargs.get("become", False))
		become_user = kwargs.get("become_user")
		timeout = kwargs.get("timeout")

		runner = AnsibleOps()
		result = runner.run_playbook(
			server_ip=host,  # either or both are fine; class resolves
			server_name=server_name,
			playbook_path=playbook_arg,  # supports short names via _resolve_playbook_path
			extra_vars=extra_vars,
			become=become,
			become_user=become_user,
			timeout=int(timeout) if timeout else None,
		)

		ok = bool(result.get("ok"))

		if server_name:
			server_docname = server_name
		else:
			server_docname = frappe.db.get_value("Server", {"server_ip": host}, "name")
			if not server_docname:
				frappe.throw(f"No Server document found with server_ip={host}")

		log_id = log_ansible_result(
			result_json=result,
			operation="Playbook",
			server=server_docname,
			bench=None,
			site=extra_vars.get("site_name"),
		)

		return {
			"status": "success" if ok else "error",
			"ok": ok,
			"server": server_docname,
			"message": f"Playbook executed on {server_docname}",
			"log_id": log_id,
			"data": result,
		}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "run_playbook API error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def ping_server(**kwargs):
	"""
	Ping a remote server via Ansible and log the result.

	Accepted args (one of host or server_name is required):
	  - host:        server IP / DNS (alias: server_ip)
	  - server_name: name of Server doctype record (primary key)

	Optional (class will auto-resolve from Server doctype if omitted):
	  - user
	  - port
	  - private_key
	"""
	try:
		host = kwargs.get("host") or kwargs.get("server_ip")
		server_name = kwargs.get("server_name")

		if not host and not server_name:
			frappe.throw("Provide either 'host' (server_ip) or 'server_name'")

		runner = AnsibleOps()
		result = runner.run_ping(
			server_ip=host,
			server_name=server_name,
		)

		ok = bool(result.get("ok"))
		status = "Verified" if ok else "Failed"

		if server_name:
			server_docname = server_name
		else:
			server_docname = frappe.db.get_value("Server", {"server_ip": host}, "name")
			if not server_docname:
				frappe.throw(f"No Server document found with server_ip={host}")

		frappe.db.set_value(
			"Server",
			server_docname,
			{"verify_status": status, "last_verified_at": frappe.utils.now_datetime()},
		)
		frappe.db.commit()

		log_id = log_ansible_result(
			result_json=result,
			operation="Ping",
			server=server_docname,
		)

		return {
			"status": "success" if ok else "error",
			"ok": ok,
			"server": server_docname,
			"message": f"Ping executed on {server_docname}",
			"log_id": log_id,
		}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "ping_server API error")
		return {"status": "error", "message": str(e)}
