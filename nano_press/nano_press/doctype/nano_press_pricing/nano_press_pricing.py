# Copyright (c) 2026, Venkatesh M and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class NanoPressPricing(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		currency: DF.Literal["USD", "INR", "EUR", "GBP"]
		enable_wallet_system: DF.Check
		initial_signup_bonus: DF.Currency
		minimum_recharge_amount: DF.Currency
		site_deployment_cost: DF.Currency
	# end: auto-generated types

	def validate(self):
		"""Ensure all amounts are positive"""
		if self.site_deployment_cost <= 0:
			frappe.throw(_("Site Deployment Cost must be greater than zero"), title=_("Invalid Amount"))

		if self.initial_signup_bonus < 0:
			frappe.throw(_("Initial Signup Bonus cannot be negative"), title=_("Invalid Amount"))

		if self.minimum_recharge_amount <= 0:
			frappe.throw(_("Minimum Recharge Amount must be greater than zero"), title=_("Invalid Amount"))

	@staticmethod
	def get_site_deployment_cost():
		"""Get the current site deployment cost"""
		pricing = frappe.get_cached_doc("Nano Press Pricing", "Nano Press Pricing")
		return pricing.site_deployment_cost

	@staticmethod
	def get_initial_bonus():
		"""Get the initial signup bonus amount"""
		pricing = frappe.get_cached_doc("Nano Press Pricing", "Nano Press Pricing")
		return pricing.initial_signup_bonus

	@staticmethod
	def get_minimum_recharge():
		"""Get the minimum recharge amount"""
		pricing = frappe.get_cached_doc("Nano Press Pricing", "Nano Press Pricing")
		return pricing.minimum_recharge_amount

	@staticmethod
	def get_currency():
		"""Get the configured currency"""
		pricing = frappe.get_cached_doc("Nano Press Pricing", "Nano Press Pricing")
		return pricing.currency

	@staticmethod
	def is_wallet_enabled():
		"""Check if wallet system is enabled"""
		pricing = frappe.get_cached_doc("Nano Press Pricing", "Nano Press Pricing")
		return pricing.enable_wallet_system
