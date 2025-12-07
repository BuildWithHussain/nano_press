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
	if not frappe.has_permission("Frappe Site", "read", site_name):
		frappe.throw("You do not have permission to access this Frappe Site", frappe.PermissionError)

	site = frappe.get_doc("Frappe Site", site_name)
	return site.get_password("admin_password")
