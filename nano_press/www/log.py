import math

import frappe


def get_context(context):
	"""Get context for log page - fetch Ansible Logs for current user."""

	user = frappe.session.user

	# Pagination
	page_length = 10
	page = frappe.form_dict.page or 1
	page = int(page)

	# Get total count
	total_logs = frappe.db.count("Ansible Log", filters={"triggered_by": user})

	# Calculate pagination
	total_pages = math.ceil(total_logs / page_length) if total_logs > 0 else 1
	start = (page - 1) * page_length

	# Get logs for current page
	logs = frappe.db.get_list(
		"Ansible Log",
		filters={"triggered_by": user},
		fields=[
			"name",
			"operation",
			"server_name",
			"status",
			"rc",
			"triggered_by",
			"executed_on",
			"site_name",
			"bench_name",
			"creation",
			"modified",
		],
		order_by="executed_on desc",
		limit_start=start,
		limit_page_length=page_length,
	)

	context.logs = logs
	context.user = user
	context.page = page
	context.total_pages = total_pages
	context.total_logs = total_logs
	context.page_length = page_length
	context.has_prev = page > 1
	context.has_next = page < total_pages

	return context
