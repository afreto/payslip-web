// tabs preferred
(() => {
	const openBtn = document.getElementById('open');
	const dlg = document.getElementById('cred');
	const form = document.getElementById('credform');
	const cancel = document.getElementById('cancel');
	const status = document.getElementById('status');

	function setStatus(msg) { status.textContent = msg || ''; }

	function rid() {
		// simple RFC4122-ish; fine for correlating logs
		return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
			const r = Math.random()*16|0, v = c === 'x' ? r : (r&0x3|0x8);
			return v.toString(16);
		});
	}

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

		const requestId = rid();
		console.debug('[UI] starting run', { requestId });

		dlg.close();
		setStatus('Starting… this may take a few minutes depending on how many payslips you have.');

		try {
			const resp = await fetch('/run', {
				method: 'POST',
				headers: {
					'Content-Type': 'application/x-www-form-urlencoded',
					'X-Request-ID': requestId
				},
				body: new URLSearchParams({ username, password }).toString()
			});

			const ridResp = resp.headers.get('X-Request-ID') || requestId;

			if (!resp.ok) {
				const text = await resp.text().catch(() => '');
				console.error('[UI] run failed', { status: resp.status, rid: ridResp, body: text });
				if (resp.status === 404) return setStatus(`No payslips found or login failed. Request-ID=${ridResp}`);
				if (resp.status === 400) return setStatus('Username and password are required.');
				return setStatus(`Error while fetching payslips. Request-ID=${ridResp}`);
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
			console.debug('[UI] download started', { rid: ridResp });
			setStatus('Download started.');
		} catch (err) {
			console.error('[UI] network error', err);
			setStatus('Network error.');
		}
	});
})();
