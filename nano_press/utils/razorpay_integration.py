import frappe
from frappe import _


def create_wallet_recharge_order(user, amount):
	from razorpay_frappe.razorpay_integration.doctype.razorpay_order.razorpay_order import RazorpayOrder

	result = RazorpayOrder.initiate(
		amount=amount,
		currency="INR",
		meta_data={"user_id": user, "recharge_type": "wallet_topup", "module": "nano_press"},
		ref_dt="Nano Press Wallet",
		ref_dn=user,
	)

	return result


def handle_razorpay_order_update(razorpay_order, method):
	if razorpay_order.status == "Paid" and razorpay_order.ref_dt == "Nano Press Wallet":
		user = razorpay_order.ref_dn

		if frappe.db.exists("Wallet Transaction", {"razorpay_order": razorpay_order.name}):
			return

		from nano_press.utils.wallet_manager import credit_wallet

		credit_wallet(
			user=user,
			amount=razorpay_order.amount,
			razorpay_order_id=razorpay_order.name,
			description=f"Wallet recharge via Razorpay (Order: {razorpay_order.order_id})",
		)


def get_razorpay_key_id():
	return frappe.db.get_single_value("Razorpay Settings", "key_id")
