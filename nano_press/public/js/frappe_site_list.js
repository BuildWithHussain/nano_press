frappe.listview_settings['Frappe Site'] = {
	onload: function(listview) {
		frappe.call({
			method: 'nano_press.api.get_wallet_balance',
			callback: function(r) {
				if (r.message) {
					const balance = r.message.balance;
					frappe.call({
						method: 'nano_press.api.get_deployment_pricing',
						callback: function(p) {
							if (p.message) {
								const currency = p.message.currency;
								const cost = p.message.deployment_cost;
								const indicator = balance >= cost ? 'green' : 'red';

								listview.page.add_inner_message(
									`Wallet Balance: ${currency} ${balance.toFixed(2)}`,
									indicator
								);

								if (balance < cost) {
									listview.page.add_inner_message(
										`<a href="/wallet" class="text-blue-600 hover:text-blue-800">Recharge Wallet</a> to deploy sites`,
										'orange'
									);
								}
							}
						}
					});
				}
			}
		});
	}
};
