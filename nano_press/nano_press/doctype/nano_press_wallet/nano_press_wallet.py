# Copyright (c) 2026, Venkatesh M and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class NanoPressWallet(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		balance: DF.Currency
		created_at: DF.Datetime | None
		is_active: DF.Check
		total_credited: DF.Currency
		total_debited: DF.Currency
		user: DF.Link
	# end: auto-generated types

	def validate(self):
		"""Ensure balance never goes negative"""
		if self.balance < 0:
			frappe.throw(
				_("Wallet balance cannot be negative. Current balance: {0}").format(self.balance),
				title=_("Invalid Balance")
			)

	@staticmethod
	def get_balance(user):
		"""Get current wallet balance for a user"""
		if not frappe.db.exists("Nano Press Wallet", user):
			return 0.0

		wallet = frappe.get_cached_doc("Nano Press Wallet", user)
		return wallet.balance

	@staticmethod
	def can_deploy_site(user, cost):
		"""Check if user has sufficient balance to deploy a site"""
		balance = NanoPressWallet.get_balance(user)
		return balance >= cost

	def has_permission(doc, ptype, user=None):
		"""Row-level permission: users can only read their own wallet"""
		if not user:
			user = frappe.session.user

		# System Manager has full access
		if "System Manager" in frappe.get_roles(user):
			return True

		# Users can only read their own wallet
		if ptype == "read" and doc.user == user:
			return True

		return False
