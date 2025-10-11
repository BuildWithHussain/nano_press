import json

import frappe

from nano_press.nano_press.doctype.ansible_log.ansible_log import log_ansible_result
from nano_press.nano_press.utils.ansible.src.AnsibleRunner import AnsibleOps


@frappe.whitelist()
def run_playbook(**kwargs):
	"""
	Run a playbook remotely on a given server.
	Example payload:
	{
	  "host": "192.168.1.10",
	  "user": "frappe",
	  "port": 22,
	  "private_key": "/home/frappe/.ssh/id_rsa",
	  "playbook_path": "/opt/frappe_docker/deploy.yml",
	  "extra_vars": {"site_name": "erp.example.com"},
	  "become": true
	}
	"""
	try:
		host = kwargs.get("host")
		user = kwargs.get("user", "frappe")
		port = int(kwargs.get("port", 22))
		playbook = kwargs.get("playbook_path")
		key = kwargs.get("private_key")
		extra_vars = kwargs.get("extra_vars", {})
		become = bool(kwargs.get("become", False))

		runner = AnsibleOps()
		result = runner.run_playbook(
			host=host,
			user=user,
			port=port,
			playbook_path=playbook,
			private_key=key,
			extra_vars=extra_vars,
			become=become,
		)
		server_doc = frappe.get_doc("Server", {"server_ip": host})
		server_name = server_doc.server_name
		log_id = log_ansible_result(result, operation="Playbook", server=server_name, bench=None, site=None)
		return {
			"status": "success",
			"message": f"Playbook executed on {server_name}",
			"log_id": log_id,
		}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "deploy_playbook API error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def ping_server(**kwargs):
	"""
	Ping a remote server via Ansible and log the result.

	Example API Payload:
	{
	  "host": "192.168.1.10",
	  "user": "frappe",
	  "port": 22,
	  "private_key": "/home/frappe/.ssh/id_rsa"
	}
	"""

	try:
		host = kwargs.get("host")
		user = kwargs.get("user", "frappe")
		port = int(kwargs.get("port", 22))
		private_key = kwargs.get("private_key")

		if not host:
			frappe.throw("Missing required field: host")

		runner = AnsibleOps()
		result = runner.run_ping(
			host=host,
			user=user,
			port=port,
			private_key=private_key,
		)
		server_doc = frappe.get_doc("Server", {"server_ip": host})
		server_name = server_doc.server_name

		log_id = log_ansible_result(
			result_json=result,
			operation="Ping",
			server=server_name,
		)
		return {
			"status": "success",
			"message": f"Ping executed successfully on {server_name}",
			"log_id": log_id,
			"data": result,
		}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "ping_server API error")
		return {"status": "error", "message": str(e)}
