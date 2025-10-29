// tabs preferred
(() => {
	const openBtn = document.getElementById('open');
	const dlg = document.getElementById('cred');
	const form = document.getElementById('credform');
	const cancel = document.getElementById('cancel');
	const status = document.getElementById('status');

	function setStatus(msg) { status.textContent = msg || ''; }

	openBtn.addEventListener('click', () => {
		dlg.showModal();
		setStatus('');
	});

	cancel.addEventListener('click', () => dlg.close());

	form.addEventListener('submit', async (e) => {
		e.preventDefault();
		const formData = new FormData(form);
		const username = formData.get('username')?.toString().trim();
		const password = formData.get('password')?.toString().trim();
		if (!username || !password) return;

		dlg.close();
		setStatus('Starting… this may take a few minutes depending on how many payslips you have.');

		try {
			const resp = await fetch('/run', {
				method: 'POST',
				headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
				body: new URLSearchParams({ username, password }).toString()
			});

			if (!resp.ok) {
				if (resp.status === 404) return setStatus('No payslips found or login failed.');
				if (resp.status === 400) return setStatus('Username and password are required.');
				return setStatus('Error while fetching payslips.');
			}

			const blob = await resp.blob();
			const url = URL.createObjectURL(blob);
			const a = document.createElement('a');
			a.href = url;
			a.download = resp.headers.get('Content-Disposition')?.match(/filename="(.+?)"/)?.[1] || 'payslips.zip';
			document.body.appendChild(a);
			a.click();
			a.remove();
			URL.revokeObjectURL(url);
			setStatus('Download started.');
		} catch {
			setStatus('Network error.');
		}
	});
})();
