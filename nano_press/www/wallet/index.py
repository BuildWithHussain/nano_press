import frappe


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.throw("Please login to view wallet", frappe.PermissionError)

	from nano_press.nano_press.doctype.nano_press_pricing.nano_press_pricing import NanoPressPricing
	from nano_press.utils.wallet_manager import get_user_balance

	user = frappe.session.user
	balance = get_user_balance(user)
	deployment_cost = NanoPressPricing.get_site_deployment_cost()

	context.balance = balance
	context.deployment_cost = deployment_cost
	context.low_balance = balance < deployment_cost
	context.required_amount = deployment_cost - balance if balance < deployment_cost else 0
	context.currency = NanoPressPricing.get_currency()
	context.min_recharge = NanoPressPricing.get_minimum_recharge()

	context.transactions = frappe.get_all(
		"Wallet Transaction",
		filters={"user": user},
		fields=["name", "transaction_type", "amount", "balance_after", "description", "transaction_date"],
		order_by="transaction_date desc",
		limit=10,
	)

	return context
