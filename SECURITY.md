# Security
Keep the project ID in local `.env` or Streamlit secrets and commit only placeholder examples.
Use the existing Earth Engine login locally. Keep credentials out of the repository and logs.
For deployment, use a dedicated project and a service account with Earth Engine Resource Viewer and Service Usage Consumer. [Google IAM guidance](https://developers.google.com/earth-engine/guides/access_control)
Area analysis, monthly trends and planting scenarios share one 10-second cooldown per session. New sessions and concurrent users can still consume quota. Monitor project quotas in Google Cloud Console.
Each live data cache holds up to 50 results for 24 hours. Only derived public observations are cached. Study coordinates can remain in server memory during that period.
Earth Engine API sockets time out after 90 seconds of inactivity. The SDK allows two retries with randomized exponential backoff for transient failures. End-to-end latency can exceed one minute, and a client timeout can leave server-side work running.
Use the standard logging configuration. App errors record the operation and exception class. Google API retry diagnostics omit URLs and payloads.
Rotate a deployment key after grading or suspected exposure. Provision its replacement, update the deployment secret, restart the app to clear cached authentication, verify access, then revoke the old key in IAM.
