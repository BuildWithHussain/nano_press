def get_context(context):
	"""Get context for my sites page"""

	# Hardcoded sites data for now
	context.sites = [
		{
			"name": "erp.mycompany.com",
			"status": "Active",
			"server": "Production Server 1",
			"apps": ["frappe", "erpnext", "hrms"],
			"created": "2024-01-15",
			"last_updated": "2024-10-28",
			"version": "v15.0.0",
		},
		{
			"name": "staging.mycompany.com",
			"status": "Active",
			"server": "Staging Server",
			"apps": ["frappe", "erpnext"],
			"created": "2024-03-20",
			"last_updated": "2024-10-25",
			"version": "v15.0.0",
		},
		{
			"name": "dev.mycompany.com",
			"status": "Inactive",
			"server": "Development Server",
			"apps": ["frappe", "custom_app"],
			"created": "2024-05-10",
			"last_updated": "2024-09-15",
			"version": "v14.0.0",
		},
		{
			"name": "crm.sales.com",
			"status": "Active",
			"server": "Production Server 2",
			"apps": ["frappe", "crm"],
			"created": "2024-02-28",
			"last_updated": "2024-10-29",
			"version": "v15.0.0",
		},
	]

	context.page_title = "My Sites"

	return context
