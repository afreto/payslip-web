# tabs preferred
from flask import Flask, render_template, request, send_file, abort
from werkzeug.middleware.proxy_fix import ProxyFix
import tempfile, os, io, zipfile, time

from scraper import run_scrape

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

@app.get("/")
def index():
	return render_template("index.html")

@app.post("/run")
def run():
	username = (request.form.get("username") or "").strip()
	password = (request.form.get("password") or "").strip()
	if not username or not password:
		abort(400, "Username and password are required.")

	# Per-request temp workspace; nothing persisted, creds never saved
	with tempfile.TemporaryDirectory(prefix="payslips_") as workdir:
		out_dir = os.path.join(workdir, "downloads")
		os.makedirs(out_dir, exist_ok=True)

		try:
			total = run_scrape(username=username, password=password, out_dir=out_dir)
		except Exception:
			abort(500, "Unexpected error while fetching payslips.")

		if total == 0:
			abort(404, "No payslips found or login failed.")

		# Zip the results into memory and return
		mem = io.BytesIO()
		with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
			for root, _, files in os.walk(out_dir):
				for fn in files:
					fp = os.path.join(root, fn)
					arc = os.path.relpath(fp, out_dir)
					zf.write(fp, arc)
		mem.seek(0)

		filename = f"payslips_{int(time.time())}.zip"
		return send_file(
			mem,
			mimetype="application/zip",
			as_attachment=True,
			download_name=filename
		)
