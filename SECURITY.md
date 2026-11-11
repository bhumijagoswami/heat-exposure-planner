# Security
Keep the project ID in local `.env` or Streamlit secrets and commit only placeholder examples.
Use the existing Earth Engine login locally. Keep credentials out of the repository and logs.
For deployment, use a dedicated project and a service account with Earth Engine Resource Viewer and Service Usage Consumer. [Google IAM guidance](https://developers.google.com/earth-engine/guides/access_control)
Monitor Earth Engine compute and request quotas in Google Cloud Console.
Rotate a deployment key after grading or suspected exposure. Provision its replacement, update the deployment secret, verify access, then revoke the old key in IAM.
