window.NanoPressWallet = {
	async getBalance() {
		const response = await frappe.call({
			method: 'nano_press.api.get_wallet_balance',
		});
		return response.message;
	},

	async createRechargeOrder(amount) {
		const response = await frappe.call({
			method: 'nano_press.api.create_recharge_order',
			args: { amount: amount },
		});
		return response.message;
	},

	async getRazorpayKey() {
		const response = await frappe.call({
			method: 'nano_press.api.get_razorpay_key',
		});
		return response.message.key_id;
	},

	openCheckout(orderId, keyId, amount, currency = 'INR') {
		const options = {
			key: keyId,
			order_id: orderId,
			amount: amount * 100,
			currency: currency,
			name: 'Nano Press',
			description: 'Wallet Recharge',
			handler: (response) => {
				frappe.show_alert({
					message: 'Payment successful! Wallet will be credited shortly.',
					indicator: 'green',
				});
				setTimeout(() => location.reload(), 2000);
			},
			prefill: {
				email: frappe.session.user_email,
			},
			theme: {
				color: '#2563eb',
			},
			modal: {
				ondismiss: () => {
					console.log('Payment cancelled');
				},
			},
		};

		const rzp = new Razorpay(options);
		rzp.open();
	},
};
