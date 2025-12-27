# Copyright (c) 2025, Build With Hussain and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class AppVersion(Document):
	def autoname(self):
		if self.version:
			self.scrubbed_version = self.version.lower().replace(" ", "-")
			self.name = self.scrubbed_version
