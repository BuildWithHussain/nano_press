(() => {
	window.frappeInstaller = () => ({
		currentStep: 1,
		stepNames: ['Server', 'Apps', 'Domain', 'Deploy'],
		showAdvanced: false,

		serverDetails: {
			ip: '',
			rootUser: 'root',
			sshPort: '22',
		},

		generatedSSHKey:
			'ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC7... frappe@deploy',

		frappeVersion: 'version-15',
		availableApps: [
			{ id: 'erpnext', name: 'ERPNext', desc: 'ERP System' },
			{ id: 'hrms', name: 'HRMS', desc: 'HR Management' },
			{ id: 'lms', name: 'LMS', desc: 'Learning' },
			{ id: 'crm', name: 'CRM', desc: 'Customer Relations' },
		],
		selectedApps: [],
		customApps: [],
		showCustomAppDialog: false,
		appType: 'public',
		customAppForm: {
			name: '',
			githubUrl: '',
			token: '',
			branch: 'main',
		},

		domain: '',

		deploying: false,
		deployComplete: false,
		deployStep: 0,
		deploymentStatus: 'Preparing server...',

		copied: false,

		copyToClipboard() {
			navigator.clipboard.writeText(this.generatedSSHKey).then(() => {
				this.copied = true;
				setTimeout(() => {
					this.copied = false;
				}, 2000);
			});
		},

		toggleApp(appId) {
			const index = this.selectedApps.indexOf(appId);
			if (index > -1) {
				this.selectedApps.splice(index, 1);
			} else {
				this.selectedApps.push(appId);
			}
		},

		addCustomApp() {
			this.customApps.push({
				name: this.customAppForm.name,
				githubUrl: this.customAppForm.githubUrl,
				token: this.appType === 'private' ? this.customAppForm.token : '',
				branch: this.customAppForm.branch || 'main',
			});
			this.customAppForm = {
				name: '',
				githubUrl: '',
				token: '',
				branch: 'main',
			};
			this.appType = 'public';
			this.showCustomAppDialog = false;
		},

		removeCustomApp(index) {
			this.customApps.splice(index, 1);
		},

		getSelectedAppsNames() {
			const appNames = this.selectedApps.map((id) => {
				const app = this.availableApps.find((a) => a.id === id);
				return app ? app.name : '';
			});
			const allApps = [...appNames, ...this.customApps.map((a) => a.name)];
			return allApps.join(', ') || 'None';
		},

		startDeployment() {
			this.deploying = true;
			this.deployStep = 0;

			setTimeout(() => {
				this.deployStep = 1;
				this.deploymentStatus = 'Preparing server...';
			}, 1000);

			setTimeout(() => {
				this.deployStep = 2;
				this.deploymentStatus = 'Deploying site...';
			}, 3000);

			setTimeout(() => {
				this.deploying = false;
				this.deployComplete = true;
			}, 5000);
		},

		visitSite() {
			const siteUrl = this.domain || this.serverDetails.ip;
			alert(`Opening site: ${siteUrl}`);
		},

		nextStep() {
			if (this.currentStep < 4) {
				this.currentStep++;
			}
		},

		prevStep() {
			if (this.currentStep > 1) {
				this.currentStep--;
			}
		},
	});
})();
