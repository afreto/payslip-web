from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, FileResponse, PlainTextResponse
import tempfile, os, subprocess, sys, shutil, zipfile, pathlib, uuid
from starlette.responses import RedirectResponse

application = FastAPI()

HTML_PAGE = """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Payslip Downloader</title>
    <style>
      body { font-family: system-ui, -apple-system, Arial; max-width: 720px; margin: 4rem auto; padding: 1rem; }
      .card { border: 1px solid #e6e6e6; padding: 1.25rem; border-radius: 8px; }
      label { display:block; margin-top: .75rem; }
      input { width:100%; padding: .5rem; margin-top: .25rem; }
      button { margin-top: 1rem; padding: .6rem 1rem; }
      .hint { color:#666; font-size: .9rem; }
    </style>
  </head>
  <body>
    <div class="card">
      <h1>Payslip Downloader</h1>
      <p class="hint">Enter your CoreHR username and password. The server will run the grabber and return a ZIP of your payslips.</p>
      <form method="post" action="/download">
        <label>Username
          <input name="username" type="text" required />
        </label>
        <label>Password
          <input name="password" type="password" required />
        </label>
        <button type="submit">Download Payslips</button>
      </form>
      <p class="hint">Note: This runs the existing grabber on the server and streams a ZIP back. Do not reuse passwords you don't trust.</p>
    </div>
  </body>
</html>
"""


@application.get("/", response_class=HTMLResponse)
async def index():
    return HTML_PAGE


@application.post("/download")
async def download(username: str = Form(...), password: str = Form(...)):
    # Basic validation
    if not username or not password:
        return PlainTextResponse("username and password required", status_code=400)

    # Create an isolated temporary working area
    with tempfile.TemporaryDirectory(prefix="payslip-run-") as tmpdir:
        tmpdir_path = pathlib.Path(tmpdir)
        creds_path = tmpdir_path / "credentials.env"
        output_dir = tmpdir_path / "boohoo_payslips"
        user_data_dir = tmpdir_path / "corehr_user_data"
        output_dir.mkdir(exist_ok=True)
        user_data_dir.mkdir(exist_ok=True)

        # Write credentials file expected by the grabber
        creds_text = f"USERNAME={username}\nPASSWORD={password}\n"
        creds_path.write_text(creds_text, encoding="utf-8")

        # Prepare environment for subprocess
        env = os.environ.copy()
        env["CREDENTIALS_ENV"] = str(creds_path)
        env["BASE_DIR"] = str(output_dir)
        env["USER_DATA_DIR"] = str(user_data_dir)

        # Run the existing grabs script as a subprocess. Use same Python executable.
        # We'll run it from the project root (assumed current working dir in container)
        run_cmd = [sys.executable, "payslips_grabber.py"]
        try:
            proc = subprocess.run(run_cmd, cwd=os.getcwd(), env=env, capture_output=True, text=True, timeout=600)
        except subprocess.TimeoutExpired:
            return PlainTextResponse("Grabber timed out after 10 minutes", status_code=504)

        # If the process failed, return logs for debugging
        if proc.returncode != 0:
            # include stdout/stderr
            text = "Grabber failed on the server. Return code: {}\n\nSTDOUT:\n{}\n\nSTDERR:\n{}".format(proc.returncode, proc.stdout or "(empty)", proc.stderr or "(empty)")
            return PlainTextResponse(text, status_code=500)

        # Zip the output directory (if any files)
        # Walk the output_dir and create a zip file
        zip_name = tmpdir_path / f"payslips_{uuid.uuid4().hex}.zip"
        found_any = False
        with zipfile.ZipFile(zip_name, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(output_dir):
                for fname in files:
                    found_any = True
                    fpath = os.path.join(root, fname)
                    arcname = os.path.relpath(fpath, output_dir)
                    zf.write(fpath, arcname)

        if not found_any:
            return PlainTextResponse("No payslips were downloaded by the grabber.", status_code=204)

        # Return the zip as a file response (browser will download)
        return FileResponse(str(zip_name), media_type="application/zip", filename=zip_name.name)
