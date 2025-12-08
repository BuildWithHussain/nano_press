# Copyright (c) 2025, Venkatesh M and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class Apps(Document):
	def before_insert(self):
		self.scrubbed_name = self.app_name.replace(" ", "_").lower()
