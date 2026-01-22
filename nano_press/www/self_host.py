import frappe

from nano_press.nano_press.doctype.server.server import Server


def get_context(context):
	context.public_key = Server._read_local_public_key()
	context.apps = get_apps()
	context.user_email = frappe.session.user
	context.user_servers = get_user_servers()
	context.frappe_versions = get_frappe_versions()
	return context


def get_user_servers():
	return frappe.get_all(
		"Server",
		filters={"owner": frappe.session.user},
		fields=["name", "server_ip", "ssh_user", "ssh_port", "verify_status"],
		order_by="creation desc",
	)


def get_apps():
	return frappe.get_all(
		"Apps",
		filters={"is_public": 1, "enabled": 1},
		fields=["name", "branch", "repo_url", "scrubbed_name", "frappe", "app_logo"],
	)


def get_frappe_versions():
	return frappe.get_all(
		"App Version",
		fields=["version", "scrubbed_version"],
		order_by="creation asc",
	)
