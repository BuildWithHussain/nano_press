# Copyright (c) 2026, Venkatesh M and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class WalletTransaction(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		amount: DF.Currency
		balance_after: DF.Currency | None
		balance_before: DF.Currency | None
		description: DF.SmallText | None
		processed_by: DF.Link | None
		razorpay_order: DF.Link | None
		reference_doctype: DF.Link | None
		reference_name: DF.DynamicLink | None
		transaction_date: DF.Datetime | None
		transaction_type: DF.Literal["Credit", "Debit", "Refund", "Initial Bonus", "Promotion"]
		user: DF.Link
	# end: auto-generated types

	def validate(self):
		"""Prevent modifications after insert, ensure amount > 0"""
		# Ensure amount is positive
		if self.amount <= 0:
			frappe.throw(
				_("Transaction amount must be greater than zero. Amount: {0}").format(self.amount),
				title=_("Invalid Amount"),
			)

		# Prevent modifications after insert (make transaction immutable)
		if not self.is_new():
			frappe.throw(
				_("Wallet Transaction cannot be modified after creation"), title=_("Transaction Immutable")
			)

	def on_trash(self):
		"""Prevent deletion of wallet transactions"""
		frappe.throw(
			_("Wallet Transactions cannot be deleted. They are part of the immutable audit trail."),
			title=_("Cannot Delete Transaction"),
		)

	def after_insert(self):
		"""Update wallet balance after transaction is created"""
		# Get or create wallet
		wallet_name = self.user
		if not frappe.db.exists("Nano Press Wallet", wallet_name):
			# Create wallet if it doesn't exist
			wallet = frappe.get_doc(
				{
					"doctype": "Nano Press Wallet",
					"user": self.user,
					"balance": 0.0,
					"total_credited": 0.0,
					"total_debited": 0.0,
					"is_active": 1,
				}
			)
			wallet.insert(ignore_permissions=True)
		else:
			wallet = frappe.get_doc("Nano Press Wallet", wallet_name)

		# Store balance before transaction
		self.db_set("balance_before", wallet.balance, update_modified=False)

		# Update wallet balance based on transaction type
		if self.transaction_type in ["Credit", "Initial Bonus", "Promotion", "Refund"]:
			# Add to balance
			wallet.balance += self.amount
			wallet.total_credited += self.amount
		elif self.transaction_type == "Debit":
			# Subtract from balance
			if wallet.balance < self.amount:
				frappe.throw(
					_("Insufficient balance. Available: {0}, Required: {1}").format(
						wallet.balance, self.amount
					),
					title=_("Insufficient Balance"),
				)
			wallet.balance -= self.amount
			wallet.total_debited += self.amount

		# Save updated wallet
		wallet.save(ignore_permissions=True)

		# Store balance after transaction
		self.db_set("balance_after", wallet.balance, update_modified=False)

	def has_permission(doc, ptype, user=None):
		"""Row-level permission: users can only read their own transactions"""
		if not user:
			user = frappe.session.user

		# System Manager has full access
		if "System Manager" in frappe.get_roles(user):
			return True

		# Users can only read their own transactions
		if ptype == "read" and doc.user == user:
			return True

		return False
