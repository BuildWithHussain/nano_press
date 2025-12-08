// QuerySync implementation
class QuerySync {
	constructor(options = {}) {
		this.options = {
			pushState: true,
			defaultValues: {},
			...options,
		};

		this.listeners = new Set();
		this.isUpdatingFromUrl = false;
		this.isUpdatingFromState = false;

		// Initialize state with current URL parameters and default values
		this._state = this.parseQueryParams();

		// Create proxy handler
		const handler = {
			set: (target, prop, value) => {
				// Always store as string
				target[prop] = String(value);

				// Update URL if change didn't come from URL
				if (!this.isUpdatingFromUrl) {
					this.updateUrl(target);
				}

				return true;
			},
			deleteProperty: (target, prop) => {
				// Remove property
				delete target[prop];

				// Update URL if change didn't come from URL
				if (!this.isUpdatingFromUrl) {
					this.updateUrl(target);
				}

				return true;
			},
		};

		// Create proxy
		this.state = new Proxy(this._state, handler);

		// Bind methods
		this.handlePopState = this.handlePopState.bind(this);

		// Initialize event listener
		window.addEventListener('popstate', this.handlePopState);
	}

	/**
	 * Parse query parameters from the URL
	 * @returns {Object} Parsed query parameters
	 */
	parseQueryParams() {
		const searchParams = new URLSearchParams(window.location.search);
		const params = {};

		// First initialize with default values (as strings)
		for (const key of Object.keys(this.options.defaultValues)) {
			params[key] = String(this.options.defaultValues[key]);
		}

		// Then override with URL values
		for (const [key, value] of searchParams) {
			params[key] = value; // Always keep as string
		}

		return params;
	}

	/**
	 * Update URL with provided state
	 * @param {Object} state - State to update URL with
	 */
	updateUrl(state) {
		if (this.isUpdatingFromUrl) return;

		const searchParams = new URLSearchParams();

		// Add non-default values to URL
		for (const key of Object.keys(state)) {
			const value = state[key];
			const defaultValue =
				this.options.defaultValues[key] !== undefined
					? String(this.options.defaultValues[key])
					: undefined;

			// Skip default values to keep URL clean
			if (
				value !== defaultValue &&
				value !== undefined &&
				value !== null &&
				value !== ''
			) {
				searchParams.set(key, value);
			}
		}

		const newUrl = searchParams.toString()
			? `${window.location.pathname}?${searchParams.toString()}`
			: window.location.pathname;

		this.isUpdatingFromState = true;
		if (this.options.pushState) {
			window.history.pushState({}, '', newUrl);
		} else {
			window.history.replaceState({}, '', newUrl);
		}
		this.isUpdatingFromState = false;

		// Notify listeners of change
		this.notifyListeners(state);
	}

	/**
	 * Handle popstate event (browser back/forward)
	 */
	handlePopState() {
		// Skip if the popstate was triggered by our own state update
		if (this.isUpdatingFromState) return;

		this.isUpdatingFromUrl = true;
		const params = this.parseQueryParams();

		// Update internal state to match URL
		for (const key of Object.keys(this._state)) {
			delete this._state[key];
		}

		for (const key of Object.keys(params)) {
			this._state[key] = params[key];
		}

		// Notify listeners
		this.notifyListeners(this._state);
		this.isUpdatingFromUrl = false;
	}

	/**
	 * Subscribe to state changes
	 * @param {Function} callback - Function to call when state changes
	 * @returns {Function} Unsubscribe function
	 */
	subscribe(callback) {
		this.listeners.add(callback);

		// Immediately call with current state
		callback({ ...this._state });

		// Return unsubscribe function
		return () => {
			this.listeners.delete(callback);
		};
	}

	/**
	 * Notify all listeners of state change
	 * @param {Object} state - Current state
	 */
	notifyListeners(state) {
		for (const callback of this.listeners) {
			callback({ ...state });
		}
	}

	/**
	 * Reset state to default values or empty object
	 */
	reset() {
		this.isUpdatingFromUrl = true;

		// Clear current state
		for (const key of Object.keys(this._state)) {
			delete this._state[key];
		}

		// Add default values back
		for (const key of Object.keys(this.options.defaultValues)) {
			this._state[key] = String(this.options.defaultValues[key]);
		}

		// Update URL
		this.isUpdatingFromUrl = false;
		this.updateUrl(this._state);
	}

	/**
	 * Destroy the instance and clean up event listeners
	 */
	destroy() {
		window.removeEventListener('popstate', this.handlePopState);
		this.listeners.clear();
	}
}
