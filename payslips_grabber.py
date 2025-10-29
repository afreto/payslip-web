# tabs only

import os, re, pathlib, time, random
from dateutil import parser as dtparser
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ── Config ────────────────────────────────────────────────────────────────────
PORTAL_ROOT		= os.environ.get("PORTAL_ROOT", "https://my.corehr.com/pls/coreportal_boop/cp_por_public_main_page.display_login_page")
# Allow overriding output and runtime dirs via environment (used by the web wrapper)
BASE_DIR		= os.environ.get("BASE_DIR", os.path.join(os.getcwd(), "boohoo_payslips"))
USER_DATA_DIR	= os.environ.get("USER_DATA_DIR", os.path.join(os.getcwd(), "corehr_user_data"))
CREDENTIALS_ENV	= os.environ.get("CREDENTIALS_ENV", os.path.join(os.getcwd(), "credentials.env"))

# Speed & behaviour
FAST_MODE		= True
BACK_STRATEGY	= "breadcrumb"	# "breadcrumb" | "arrow" | "history"

# Optional: limit by year (inclusive). Set to None to ignore.
YEAR_FROM		= None			# e.g., 2019
YEAR_TO			= None			# e.g., 2025

# ── Timing profile with jitter (human-ish) ────────────────────────────────────
def jitter(ms_low, ms_high):
	time.sleep(random.uniform(ms_low, ms_high) / 1000.0)

if FAST_MODE:
	NETWORK_IDLE     = 4_000
	DOWNLOAD_TIMEOUT = 20_000
	SMALL_MS         = (350, 600)	 # between small clicks
	NAV_MS           = (700, 1200)	 # after opening "View"
	DL_AFTER_MS      = (200, 400)	 # after a successful download
	BACK_MS          = (600, 900)	 # after breadcrumb back
	PAGE_COOLDOWN_MS = (1500, 2500)	 # after finishing a page
else:
	NETWORK_IDLE     = 10_000
	DOWNLOAD_TIMEOUT = 35_000
	SMALL_MS         = (800, 1200)
	NAV_MS           = (1200, 2000)
	DL_AFTER_MS      = (400, 700)
	BACK_MS          = (900, 1400)
	PAGE_COOLDOWN_MS = (2500, 3500)

MAX_PAGES		= 100_000

# ── Utils ─────────────────────────────────────────────────────────────────────
def ensure_dir(p: str):
	pathlib.Path(p).mkdir(parents=True, exist_ok=True)

def log(msg: str):
	print(msg, flush=True)

def safe_filename(s: str) -> str:
	s = re.sub(r'[\\/:*?"<>|]+', '-', s)
	return re.sub(r'\s+', ' ', s).strip()

def parse_date(text: str):
	try:
		d = dtparser.parse(text, dayfirst=True, fuzzy=True)
		return d.strftime("%Y-%m-%d"), d.year
	except Exception:
		return text.strip(), None

def read_credentials(path: str):
	if not os.path.exists(path):
		raise RuntimeError(f"Credentials file not found: {path}")
	username = password = None
	with open(path, "r", encoding="utf-8") as f:
		for line in f:
			line = line.strip()
			if not line or line.startswith("#") or "=" not in line:
				continue
			key, val = line.split("=", 1)
			key = key.strip().upper()
			val = val.strip()
			if key == "USERNAME":
				username = val
			elif key == "PASSWORD":
				password = val
	if not username or not password:
		raise RuntimeError("USERNAME and/or PASSWORD missing in credentials.env")
	return username, password

# ── Locators ──────────────────────────────────────────────────────────────────
def rows_locator(page):
	return page.locator("table tbody tr")

def back_arrow(page):
	return page.locator("i.arrow-left[coretip='Back'], i[coretip='Back']")

def breadcrumb_back(page):
	return page.locator("span.nav:has-text('All My Payslips'), span.nav[coreidx='0']")

def next_page_btn(page):
	return page.locator("i.chevron-right[coretip='Next'], i[coretip='Next']")

def view_btn_in_row(row):
	inner = row.locator("span.x-btn-inner:has-text('View')")
	return inner.locator("xpath=ancestor::span[contains(@id,'corebutton-')][1]")

def download_btn(page):
	inner = page.locator("span.x-btn-inner[coretip='Download PDF'], span.x-btn-inner:has-text('Download PDF')").first
	return inner.locator("xpath=ancestor::span[contains(@id,'corebutton-')][1]")

# ── Helpers ───────────────────────────────────────────────────────────────────
def click_safely(locator, name="element", force=False):
	if hasattr(locator, "count"):
		if locator.count() == 0:
			raise RuntimeError(f"{name} not found")
		el = locator.first
	else:
		el = locator
	el.scroll_into_view_if_needed()
	jitter(*SMALL_MS)
	el.click(force=force)
	jitter(*SMALL_MS)

def js_click(locator, name="element"):
	if locator.count() == 0:
		raise RuntimeError(f"{name} not found for js_click")
	el = locator.first
	el.scroll_into_view_if_needed()
	jitter(*SMALL_MS)
	handle = el.element_handle()
	if not handle:
		raise RuntimeError(f"{name} element_handle unavailable")
	handle.evaluate("el => el.click()")
	jitter(*SMALL_MS)

def wait_network_idle(page, t=None):
	if t is None:
		t = NETWORK_IDLE
	try:
		page.wait_for_load_state("networkidle", timeout=t)
	except PWTimeout:
		pass

def on_payslips_list(page) -> bool:
	return rows_locator(page).count() > 0

def wait_table_visible(page, timeout_ms=12_000):
	start = time.time()
	while time.time() - start < timeout_ms / 1000:
		try:
			if on_payslips_list(page):
				return True
		except Exception:
			pass
		time.sleep(0.2 if FAST_MODE else 0.3)
	return False

def get_row_count(page) -> int:
	return rows_locator(page).count()

def nth_row(page, idx):
	return rows_locator(page).nth(idx)

def date_text_for_row(row) -> str:
	return row.locator("td").nth(0).inner_text().strip()

def make_target_path(base_dir, date_label, year):
	subdir = str(year) if year else "_unknown_year"
	out_dir = os.path.join(base_dir, subdir)
	ensure_dir(out_dir)
	filename = safe_filename(f"{date_label}_Payslip.pdf")
	return os.path.join(out_dir, filename)

# ── Login + Navigate via PAY button ───────────────────────────────────────────
def do_login_and_open_table(context, page, username, password):
	log("Opening portal login page…")
	page.goto(PORTAL_ROOT, wait_until="load")
	wait_network_idle(page)

	# Fill username + password
	log("Filling credentials…")
	user_in = page.locator("#p_username, input[name='p_username'][aria-label='Username']")
	pass_in = page.locator("#password-input, input[name='p_password'][aria-label='Password']")
	sign_in = page.locator("#login-button")

	if user_in.count() == 0 or pass_in.count() == 0 or sign_in.count() == 0:
		raise RuntimeError("Login fields not found on the page")

	user_in.first.fill(username)
	jitter(*SMALL_MS)
	pass_in.first.fill(password)
	jitter(*SMALL_MS)

	# Sign-in may open a new tab/window or hard-reload the app.
	existing_pages = list(context.pages)
	try:
		click_safely(sign_in, "Sign In button", force=True)
	except Exception:
		sign_in.first.click(force=True)

	# Give the dashboard time to hydrate (4–5s)
	wait_network_idle(page)
	jitter(4000, 5000)

	# If a new page opened, switch to it
	current_pages = list(context.pages)
	if len(current_pages) > len(existing_pages):
		log("Detected a new window after login — switching to newest page …")
		page = current_pages[-1]

	# Click the **Pay** tile/link (robust selectors across skins)
	log("Navigating: Pay …")
	pay_candidates = [
		"a.dashboard-link[aria-label='Pay']",
		"a.dashboard-link:has(span.tab-title:has-text('Pay'))",
		"//a[@role='link' and .//span[contains(@class,'tab-title') and normalize-space()='Pay']]",
		"a[aria-label='Pay']",
		"//a[@role='link' and normalize-space()='Pay']",
	]
	clicked = False
	for sel in pay_candidates:
		try:
			loc = page.locator(sel)
			if loc.count() > 0:
				try:
					click_safely(loc, "Pay control", force=True)
				except Exception:
					js_click(loc, "Pay control (js)")
				wait_network_idle(page)
				clicked = True
				break
		except Exception:
			continue
	if not clicked:
		# final fallback: icon with coretip
		try:
			icon = page.locator("i[coretip='Pay']")
			click_safely(icon, "Pay icon", force=True)
			wait_network_idle(page)
			clicked = True
		except Exception:
			pass
	if not clicked:
		raise RuntimeError("Could not locate a clickable ‘Pay’ control after login")

	# Click **View All** (My Payslips)
	log("Navigating: View All …")
	viewall_inner = page.locator("span.x-btn-inner:has-text('View All')")
	if viewall_inner.count() > 0:
		wrapper = viewall_inner.locator("xpath=ancestor::span[contains(@id,'corebutton-')][1]")
		try:
			click_safely(wrapper, "View All button")
		except Exception:
			js_click(wrapper, "View All button (js)")
	else:
		# fallback candidates
		viewall_fallbacks = [
			"a#corebutton-1116",
			"#corebutton-1116-btnInnerEl",
			"a[role='button']:has(span.x-btn-inner:has-text('View All'))",
			"//a[.//span[contains(@class,'x-btn-inner') and normalize-space()='View All']]",
			"text=View All",
		]
		found = False
		for sel in viewall_fallbacks:
			try:
				loc = page.locator(sel)
				if loc.count() > 0:
					try:
						click_safely(loc, "View All (fallback)", force=True)
					except Exception:
						js_click(loc, "View All (fallback js)")
					found = True
					break
			except Exception:
				continue
		if not found:
			log("   …couldn’t find ‘View All’. If you’re already on the list, that’s OK.")

	# Ensure the table is visible (retry once by clicking Pay again if necessary)
	wait_network_idle(page)
	if not wait_table_visible(page, timeout_ms=12_000):
		log("Table not visible yet — re-clicking Pay once …")
		try:
			loc = page.locator("a.dashboard-link[aria-label='Pay'], a.dashboard-link:has(span.tab-title:has-text('Pay'))")
			if loc.count() > 0:
				click_safely(loc, "Pay control (retry)", force=True)
				wait_network_idle(page)
		except Exception:
			pass

	if not wait_table_visible(page, timeout_ms=12_000):
		raise RuntimeError("Payslips table did not appear after clicking Pay/View All")

	log("✅ Reached ‘All My Payslips’ table.")
	return page

# ── Back/Next navigation ──────────────────────────────────────────────────────
def back_to_list(page):
	try:
		if BACK_STRATEGY in ("breadcrumb",):
			log("   ↩️  Back: breadcrumb …")
			loc = breadcrumb_back(page)
			try:
				click_safely(loc, "Breadcrumb ‘All My Payslips’", force=True)
			except Exception as e:
				log(f"   …breadcrumb normal failed ({e}), JS click …")
				js_click(loc, "Breadcrumb ‘All My Payslips’ (js)")
			wait_network_idle(page)
			if wait_table_visible(page):
				return True
	except Exception as e:
		log(f"   …breadcrumb methods failed: {e}")

	try:
		if BACK_STRATEGY in ("breadcrumb", "arrow"):
			log("   ↩️  Back: arrow …")
			click_safely(back_arrow(page), "Back arrow", force=True)
			wait_network_idle(page)
			if wait_table_visible(page):
				return True
	except Exception as e:
		log(f"   …Back arrow failed: {e}")

	try:
		log("   ↩️  Back: history.back() …")
		page.go_back()
		wait_network_idle(page, t=NETWORK_IDLE + 4_000)
		if wait_table_visible(page):
			return True
	except Exception as e:
		log(f"   …history.back() failed: {e}")

	return on_payslips_list(page)

def go_next_page(page) -> bool:
	btn = next_page_btn(page)
	if btn.count() == 0 or not btn.first.is_enabled():
		return False
	log("⏭️  Next page …")
	try:
		click_safely(btn, "Next page")
	except Exception as e:
		log(f"   …Next normal click failed ({e}), JS click …")
		js_click(btn, "Next page (js)")
	wait_network_idle(page)
	jitter(*SMALL_MS)
	return True

# ── Row processing ────────────────────────────────────────────────────────────
def open_and_download_row(page, row_index, base_dir):
	row = nth_row(page, row_index)
	date_text = date_text_for_row(row)
	date_label, year = parse_date(date_text)

	if YEAR_FROM and year and year < YEAR_FROM:
		log(f"➡️  [Row {row_index+1}] {date_text} — skipped (before {YEAR_FROM})")
		return False
	if YEAR_TO and year and year > YEAR_TO:
		log(f"➡️  [Row {row_index+1}] {date_text} — skipped (after {YEAR_TO})")
		return False

	target_path = make_target_path(base_dir, date_label, year)

	if os.path.exists(target_path):
		log(f"➡️  [Row {row_index+1}] {date_text} — already exists, skipping")
		return True

	log(f"➡️  [Row {row_index+1}] View → Download → Back | {date_text}")
	vbtn = view_btn_in_row(row)
	try:
		click_safely(vbtn, "View button")
	except Exception as e:
		log(f"   …View normal click failed ({e}), JS click …")
		js_click(vbtn, "View button (js)")
	wait_network_idle(page, t=NETWORK_IDLE)
	jitter(*NAV_MS)

	btn = download_btn(page)
	for attempt in range(1, 3):
		try:
			with page.expect_download(timeout=DOWNLOAD_TIMEOUT) as dl_info:
				try:
					click_safely(btn, "Download PDF")
				except Exception as e:
					log(f"   …Download normal click failed ({e}), JS click …")
					js_click(btn, "Download PDF (js)")
			dl = dl_info.value
			dl.save_as(target_path)
			log(f"   ✅ Saved: {os.path.relpath(target_path, base_dir)}")
			jitter(*DL_AFTER_MS)
			break
		except Exception as e:
			if attempt == 2:
				raise
			log("   …retrying download once…")
			jitter(800, 1600)

	if not back_to_list(page):
		raise RuntimeError("Could not return to the payslips list after download")
	wait_network_idle(page, t=NETWORK_IDLE)
	jitter(*BACK_MS)
	return True

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
	ensure_dir(BASE_DIR)
	ensure_dir(USER_DATA_DIR)
	username, password = read_credentials(CREDENTIALS_ENV)

	with sync_playwright() as pw:
		context = pw.chromium.launch_persistent_context(
			USER_DATA_DIR,
			headless=True,
			accept_downloads=True
		)
		page = context.new_page()

		log(f"FAST_MODE={FAST_MODE}, BACK_STRATEGY={BACK_STRATEGY}, YEAR_FROM={YEAR_FROM}, YEAR_TO={YEAR_TO}")
		page = do_login_and_open_table(context, page, username, password)

		total = 0
		page_no = 1

		for _ in range(MAX_PAGES):
			try:
				count = get_row_count(page)
			except Exception:
				if context.pages:
					page = context.pages[-1]
					count = get_row_count(page)
				else:
					raise

			log(f"\n📄 Page {page_no}: {count} rows.")
			if count == 0:
				break

			for i in range(count):
				try:
					if open_and_download_row(page, i, BASE_DIR):
						total += 1
					jitter(*SMALL_MS)
				except Exception as e:
					log(f"❌ Row {i+1} failed: {e}")
					if not on_payslips_list(page):
						log("   …attempting recovery Back …")
						back_to_list(page)
					wait_network_idle(page, t=NETWORK_IDLE)
					jitter(*SMALL_MS)

			jitter(*PAGE_COOLDOWN_MS)
			if not go_next_page(page):
				log("No more pages.")
				break
			page_no += 1

		log(f"\n✅ Done. Downloaded/verified {total} payslips → {BASE_DIR}\n")
		context.close()

if __name__ == "__main__":
	main()
