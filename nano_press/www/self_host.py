import frappe

from nano_press.nano_press.doctype.server.server import Server


def get_context(context):
	context.public_key = Server._read_local_public_key()
	context.apps = get_apps()
	context.user_email = frappe.session.user
	context.user_servers = get_user_servers()
	return context


def get_user_servers():
	return frappe.db.get_list(
		"Server",
		filters={"owner": frappe.session.user},
		fields=["name", "server_ip", "ssh_user", "ssh_port", "verify_status"],
		order_by="creation desc",
	)


def get_apps():
	apps = frappe.db.get_list(
		"Apps",
		filters={"is_public": 1, "enabled": 1},
		fields=["name", "branch", "repo_url", "scrubbed_name", "frappe"],
	)
	return apps
