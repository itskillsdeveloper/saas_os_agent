# SaaS OS Agent

A minimal frappe app the SaaS OS control plane installs into every tenant site.

Some plan quotas cannot be enforced from the control plane, because a user or a
file is created inside the tenant's own site, in a different process. This app
carries the one thing that has to run *there*: a `before_insert` hook on `User`
that refuses a new user once the tenant is at its plan's `max_users`.

The limit itself is not decided here. The control plane writes it into the
tenant's `site_config.json` as `saas_os_max_users`; this app only reads it and
enforces it. No limit in the config means no enforcement -- an un-provisioned
or unmanaged site behaves normally.

It deliberately does **not** enable Server Scripts. Enforcing via a server
script would require turning on `server_script_enabled` in every tenant, which
hands any tenant admin arbitrary code execution. A tiny platform-owned app is
the same enforcement without that surface.
