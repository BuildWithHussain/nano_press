import frappe

from nano_press.nano_press.doctype.server.server import Server


def get_context(context):
	context.public_key = Server._read_local_public_key()
	context.apps = get_apps()
	return context


def get_apps():
	apps = frappe.db.get_list(
		"Apps", filters={"is_public": 1, "enabled": 1}, fields=["name", "branch", "repo_url", "scrubbed_name"]
	)
	return apps
