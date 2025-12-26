# Copyright (c) 2025, Venkatesh M and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class Apps(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		app_name: DF.Data
		branch: DF.Data
		enabled: DF.Check
		frappe: DF.Check
		is_custom: DF.Check
		is_public: DF.Check
		order: DF.Int | None
		pat_token: DF.Password | None
		repo_url: DF.Data
		repository_owner: DF.Data | None
		scrubbed_name: DF.Data | None

	# end: auto-generated types

	def before_insert(self):
		self.scrubbed_name = self.app_name.replace(" ", "_").lower()

	def validate(self):
		if self.is_custom:
			if self.pat_token:
				self.is_public = 0
			else:
				self.is_public = 1
