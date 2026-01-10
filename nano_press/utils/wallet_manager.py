import frappe
from frappe import _


def initialize_user_wallet(user):
	if frappe.db.exists("Nano Press Wallet", user):
		frappe.log_error(f"Wallet already exists for user: {user}", "Wallet Initialization Skipped")
		return frappe.get_doc("Nano Press Wallet", user)

	from nano_press.nano_press.doctype.nano_press_pricing.nano_press_pricing import NanoPressPricing

	initial_bonus = NanoPressPricing.get_initial_bonus()

	wallet = frappe.get_doc(
		{
			"doctype": "Nano Press Wallet",
			"user": user,
			"balance": 0.0,
			"total_credited": 0.0,
			"total_debited": 0.0,
			"is_active": 1,
		}
	)
	wallet.insert(ignore_permissions=True)

	if initial_bonus > 0:
		transaction = frappe.get_doc(
			{
				"doctype": "Wallet Transaction",
				"user": user,
				"transaction_type": "Initial Bonus",
				"amount": initial_bonus,
				"description": f"Welcome bonus of {initial_bonus} credited on signup",
				"processed_by": "Administrator",
			}
		)
		transaction.insert(ignore_permissions=True)
		frappe.db.commit()

	return wallet


def get_user_balance(user):
	if not frappe.db.exists("Nano Press Wallet", user):
		return 0.0

	return frappe.db.get_value("Nano Press Wallet", user, "balance") or 0.0


def check_sufficient_balance(user, required_amount):
	current_balance = get_user_balance(user)

	cache_key = f"wallet_reserve:{user}"
	reservations = frappe.cache.get(cache_key) or []

	total_reserved = sum([r.get("amount", 0) for r in reservations])
	available_balance = current_balance - total_reserved

	return available_balance >= required_amount


def reserve_balance_for_deployment(user, site_name, amount):
	cache_key = f"wallet_reserve:{user}"

	current_balance = get_user_balance(user)

	existing_reservations = frappe.cache.get(cache_key) or []

	total_reserved = sum([r.get("amount", 0) for r in existing_reservations])
	available = current_balance - total_reserved

	if available < amount:
		frappe.log_error(
			f"Insufficient balance for reservation. User: {user}, Required: {amount}, Available: {available}",
			"Balance Reservation Failed",
		)
		return False

	reservation = {"site_name": site_name, "amount": amount, "timestamp": frappe.utils.now()}
	existing_reservations.append(reservation)

	frappe.cache.setex(cache_key, 1800, existing_reservations)

	return True


def release_reserved_balance(user, site_name):
	cache_key = f"wallet_reserve:{user}"

	reservations = frappe.cache.get(cache_key) or []

	updated_reservations = [r for r in reservations if r.get("site_name") != site_name]

	if updated_reservations:
		frappe.cache.setex(cache_key, 1800, updated_reservations)
	else:
		frappe.cache.delete(cache_key)


def deduct_deployment_charge(user, site_name, amount):
	current_balance = get_user_balance(user)

	if current_balance < amount:
		frappe.throw(
			_("Insufficient wallet balance. Required: {0}, Available: {1}").format(amount, current_balance),
			title=_("Insufficient Balance"),
		)

	transaction = frappe.get_doc(
		{
			"doctype": "Wallet Transaction",
			"user": user,
			"transaction_type": "Debit",
			"amount": amount,
			"reference_doctype": "Frappe Site",
			"reference_name": site_name,
			"description": f"Site deployment charge for {site_name}",
			"processed_by": frappe.session.user,
		}
	)
	transaction.insert(ignore_permissions=True)
	frappe.db.commit()

	release_reserved_balance(user, site_name)

	return transaction


def credit_wallet(user, amount, razorpay_order_id, description):
	transaction = frappe.get_doc(
		{
			"doctype": "Wallet Transaction",
			"user": user,
			"transaction_type": "Credit",
			"amount": amount,
			"razorpay_order": razorpay_order_id,
			"description": description,
			"processed_by": "Administrator",
		}
	)
	transaction.insert(ignore_permissions=True)
	frappe.db.commit()

	return transaction


def refund_deployment_charge(site_name, reason):
	transactions = frappe.get_all(
		"Wallet Transaction",
		filters={
			"reference_doctype": "Frappe Site",
			"reference_name": site_name,
			"transaction_type": "Debit",
		},
		fields=["name", "user", "amount", "transaction_date"],
	)

	if not transactions:
		return None

	original_transaction = transactions[0]

	time_since_charge = frappe.utils.time_diff_in_hours(
		frappe.utils.now(), original_transaction.get("transaction_date")
	)

	if time_since_charge > 1:
		return None

	refund = frappe.get_doc(
		{
			"doctype": "Wallet Transaction",
			"user": original_transaction.get("user"),
			"transaction_type": "Refund",
			"amount": original_transaction.get("amount"),
			"reference_doctype": "Frappe Site",
			"reference_name": site_name,
			"description": f"Refund for {site_name}: {reason}",
			"processed_by": frappe.session.user,
		}
	)
	refund.insert(ignore_permissions=True)
	frappe.db.commit()

	return refund
