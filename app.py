# tabs preferred
import os, io, zipfile, time, tempfile, uuid, logging, traceback
from flask import Flask, render_template, request, send_file, abort, make_response
from werkzeug.middleware.proxy_fix import ProxyFix
from scraper import run_scrape

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
	level=getattr(logging, LOG_LEVEL, logging.INFO),
	format="%(asctime)s %(levelname)s %(name)s %(message)s",
	force=True,  # <<— important: override gunicorn handlers
)
log = logging.getLogger("app")

DEBUG_RESPONSES = os.getenv("DEBUG", "0") == "1"

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

@app.get("/healthz")
def healthz():
	return "ok", 200

@app.get("/")
def index():
	return render_template("index.html")

@app.post("/run")
def run():
	req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
	log.info(f"[{req_id}] /run start")

	username = (request.form.get("username") or "").strip()
	password = (request.form.get("password") or "").strip()
	if not username or not password:
		log.warning(f"[{req_id}] missing creds")
		resp = make_response("Username and password are required.", 400)
		resp.headers["X-Request-ID"] = req_id
		return resp

	with tempfile.TemporaryDirectory(prefix=f"payslips_{req_id}_") as workdir:
		out_dir = os.path.join(workdir, "downloads")
		os.makedirs(out_dir, exist_ok=True)

		try:
			log.info(f"[{req_id}] calling run_scrape out_dir={out_dir}")
			total, trace_path = run_scrape(
				username=username,
				password=password,
				out_dir=out_dir,
				req_id=req_id
			)
			log.info(f"[{req_id}] run_scrape done total={total} trace={trace_path}")

			if total == 0:
				msg = f"No payslips found or login failed. Request-ID={req_id}"
				log.warning(f"[{req_id}] {msg}")
				resp = make_response(msg, 404)
				resp.headers["X-Request-ID"] = req_id
				return resp

			mem = io.BytesIO()
			with zipfile.ZipFile(mem, "w", compression=zipfile.ZIP_DEFLATED) as zf:
				for root, _, files in os.walk(out_dir):
					for fn in files:
						fp = os.path.join(root, fn)
						arc = os.path.relpath(fp, out_dir)
						zf.write(fp, arc)
			mem.seek(0)
			filename = f"payslips_{int(time.time())}.zip"
			resp = send_file(mem, mimetype="application/zip", as_attachment=True, download_name=filename)
			resp.headers["X-Request-ID"] = req_id
			return resp

		except Exception as e:
			log.error(f"[{req_id}] scrape error: {e}")
			log.debug("".join(traceback.format_exc()))
			msg = f"Error while fetching payslips. Request-ID={req_id}"
			if DEBUG_RESPONSES:
				msg += f" | {e}"
			resp = make_response(msg, 500)
			resp.headers["X-Request-ID"] = req_id
			return resp
