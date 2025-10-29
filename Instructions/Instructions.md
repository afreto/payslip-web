Deploying service on Google Cloud Run with a Web Interface
The objective is to deploy an existing project, as a serverless web service on Google Cloud Run to facilitate the secure download of documents via a single-button web interface.
System Workflow
Web Interface: A simple web page is hosted, featuring a single, prominent button labeled for document download.
Authentication Pop-up: Clicking the download button triggers a modal or pop-up window.
Credential Entry: Users are prompted to enter a Name/Username and Password within the pop-up.
Backend Execution (Cloud Run): Upon successful submission of credentials:
The web interface sends an authenticated request to the deployed Cloud Run service.
The grab_payslips_corehr.py script runs on the Cloud Run instance, using the provided credentials to fetch the documents.
Document Delivery: The Cloud Run service bundles all retrieved documents and streams them back to the user's browser, initiating a direct download to the user's local device.
Key Components and Optimizations
Google Cloud Run: Use for serverless, scalable execution of the Python script wrapped in a web framework (e.g., Flask or FastAPI). This eliminates server management overhead.
Web Framework: A small framework is necessary to handle the HTTP request, process the submitted credentials, and manage the download response.
Security:
Use HTTPS (default for Cloud Run) for encrypted credential transmission.
Validate and sanitize input (Name/Password) meticulously.
Implement secret management (e.g., Google Cloud Secret Manager) for any static script credentials, if applicable.
User Experience (UX): Provide visual feedback (e.g., "Downloading..." spinner) while the script executes, as the script's runtime will introduce a delay.
Download Mechanism: The Cloud Run service must use appropriate HTTP headers (like Content-Disposition: attachment) to force the browser to download the received file data instead of displaying it. For multiple documents, the script should zip/archive them into a single file before streaming the response.

Example Project structure is provided
Payslip Grabber Example Code - "grab_payslips_example.py"
Project name - "payslip-web"
Project ID - "payslip-web-476521"
Project number - "819671955745"

## Security notes (credentials handling)

- The web wrapper writes supplied username/password into a temporary `credentials.env` file and passes its path to the grabber. While convenient, this writes secrets to disk (albeit a temporary directory) and may be undesirable in shared or multi-tenant environments.

- Recommendations:
	- Prefer in-memory/pipe-based approaches where the grabber accepts credentials via stdin or a secure IPC channel instead of a disk file.
	- When deploying to Cloud Run or other shared infrastructure, use an authentication layer in front of the service (e.g., Cloud IAM, Cloud Endpoints) to restrict access.
	- Avoid storing long-lived credentials in images or source control. Use Secret Manager (or equivalent) for any static secrets.
	- If temporary files are unavoidable, ensure the runtime environment is ephemeral and access to tmp directories is tightly controlled.

These notes are intentionally short; adapt them to your operational security standards before deploying to production.

