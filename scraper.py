# tabs preferred
import os, re, random, time, logging
from datetime import datetime
from dateutil import parser as dtp
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

log = logging.getLogger("scraper")

LOGIN_URL = os.getenv(
	"COREHR_LOGIN_URL",
	"https://my.corehr.com/pls/coreportal_boop/cp_por_public_main_page.display_login_page"
)
HEADFUL = os.getenv("HEADFUL", "0") == "1"
SAFE_RE = re.compile(r"[^A-Za-z0-9_.\\-]")

def _safe_name(s: str) -> str:
	return SAFE_RE.sub("_", s.strip())

def _unique_path(path: str) -> str:
	base, ext = os.path.splitext(path)
	k, out = 1, path
	while os.path.exists(out):
		k += 1
		out = f"{base}({k}){ext}"
	return out

def _sleep(a=0.25, b=0.6):
	time.sleep(random.uniform(a, b))

def run_scrape(*, username: str, password: str, out_dir: str, req_id: str) -> tuple[int, str]:
	"""
	Returns (downloaded_count, trace_path)
	Trace file path is logged and left in /tmp for inspection in Cloud Logging.
	"""
	total = 0
	trace_path = f"/tmp/trace_{req_id}.zip"
	log.info(f"[{req_id}] start run_scrape LOGIN_URL={LOGIN_URL} out_dir={out_dir}")

	with sync_playwright() as pw:
		browser = pw.chromium.launch(headless=not HEADFUL, args=["--no-sandbox", "--disable-dev-shm-usage"])
		context = browser.new_context(accept_downloads=True)
		# Start tracing (screenshots & snapshots)
		try:
			context.tracing.start(screenshots=True, snapshots=True, sources=True)
		except Exception as _:
			log.warning(f"[{req_id}] tracing start failed")

		page = context.new_page()

		try:
			# 1) Login
			log.debug(f"[{req_id}] goto login")
			page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=120000)

			user_sel = "input[type='text'], input[name='username'], input#username"
			pass_sel = "input[type='password'], input[name='password'], input#password"
			submit_sel = "button[type='submit'], button:has-text('Sign in'), input[type='submit']"

			page.wait_for_selector(user_sel, timeout=30000)
			# Never log password or username
			page.fill(user_sel, username)
			page.fill(pass_sel, password)
			_sleep()
			page.click(submit_sel)
			page.wait_for_load_state("networkidle", timeout=60000)

			# Basic login error probe
			if page.locator("text=invalid").first.is_visible() or page.locator("text=incorrect").first.is_visible():
				log.warning(f"[{req_id}] login error banner detected")
				return 0, trace_path

			# 2) Pay → View All
			def click_text_first(txt: str) -> bool:
				loc = page.locator(f"text={txt}").first
				if loc.count():
					loc.click()
					return True
				return False

			if not click_text_first("Pay"):
				page.locator("role=button >> text=Pay").first.click()
			page.wait_for_load_state("networkidle", timeout=45000); _sleep()

			if not click_text_first("View All"):
				page.locator("a:has-text('View All')").first.click()
			page.wait_for_load_state("domcontentloaded", timeout=45000)

			def wait_table():
				page.wait_for_selector("table, role=table", timeout=45000)

			wait_table()

			def parse_date(s: str):
				try:
					return dtp.parse(s, dayfirst=True, fuzzy=True).date()
				except Exception:
					return None

			def rows():
				return page.locator("table >> tbody >> tr").all()

			while True:
				wait_table()
				rlist = rows()
				log.debug(f"[{req_id}] rows on page: {len(rlist)}")
				for r in rlist:
					tcells = r.locator("td")
					if tcells.count() == 0:
						continue

					date_txt = (tcells.nth(0).inner_text() or "").strip()
					dt = parse_date(date_txt) or datetime.utcnow().date()
					out_name = f"{dt.isoformat()}_Payslip.pdf"
					out_path = _unique_path(os.path.join(out_dir, str(dt.year), _safe_name(out_name)))
					os.makedirs(os.path.dirname(out_path), exist_ok=True)

					try:
						with page.expect_download(timeout=60000) as dl_info:
							r.click()
							page.wait_for_load_state("domcontentloaded", timeout=30000); _sleep()
							dl_btn = page.locator("button:has-text('Download PDF'), a:has-text('Download PDF'), text=Download PDF").first
							dl_btn.click()
						download = dl_info.value
						download.save_as(out_path)
						total += 1
						log.info(f"[{req_id}] downloaded -> {out_path}")
					except PWTimeout:
						log.warning(f"[{req_id}] timeout on row; skipping")
					finally:
						# Back to list
						for _ in range(3):
							try:
								if page.locator("a:has-text('Back')").first.is_visible():
									page.locator("a:has-text('Back')").first.click()
								elif page.locator("button[aria-label='Back']").first.is_visible():
									page.locator("button[aria-label='Back']").first.click()
								else:
									page.go_back(wait_until="domcontentloaded")
								wait_table()
								break
							except Exception:
								_sleep(0.3, 0.7)

				next_btn = page.locator("button:has-text('Next'), a:has-text('Next')").first
				if next_btn.count() and next_btn.is_enabled():
					next_btn.click()
					page.wait_for_load_state("domcontentloaded", timeout=30000); _sleep()
				else:
					break

		finally:
			# Export trace to /tmp; path will be logged in app.py
			try:
				context.tracing.stop(path=trace_path)
				log.info(f"[{req_id}] trace saved: {trace_path}")
			except Exception as _:
				log.warning(f"[{req_id}] tracing stop failed")

			context.close()
			browser.close()

	return total, trace_path
