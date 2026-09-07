app_name = "saas_os_agent"
app_title = "SaaS OS Agent"
app_publisher = "SaaS OS"
app_description = "In-tenant governance agent: enforces plan quotas inside the tenant site."
app_email = "ops@example.com"
app_license = "mit"

# The whole reason this app exists: a hook that runs inside the tenant site,
# where the control plane cannot. Keep this list tiny -- every entry is code
# the platform is responsible for on someone else's site.
doc_events = {
	"User": {
		"before_insert": "saas_os_agent.enforce.enforce_user_quota",
	},
}
