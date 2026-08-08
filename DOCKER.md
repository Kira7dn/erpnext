# Run the checked-out ERPNext source with Docker

This wrapper keeps the ERPNext source in this repository and uses the Frappe
bench/container runtime pattern from `frappe_docker`.

## Start

PowerShell:

```powershell
.\docker-start.ps1
```

Git Bash:

```bash
powershell.exe -ExecutionPolicy Bypass -File ./docker-start.ps1
```

The PowerShell script is the canonical launcher. It reads the flat UTF-8
`config.yml`, exports its values for Compose, validates the rendered Compose
configuration, and starts the stack.

Open <http://localhost:8080> and sign in with:

- User: `Administrator`
- Password: the value of `admin_password` in `config.yml`

The first startup creates the `frontend` site and can take several minutes.

## Useful commands

```bash
docker compose ps
docker compose logs -f create-site
docker compose logs -f backend
docker compose down
```

PowerShell equivalents:

```powershell
.\docker-start.ps1 -Action ps
.\docker-start.ps1 -Action logs -FollowLogs
.\docker-start.ps1 -Action down
```

The local `./erpnext` directory is mounted read-only at
`/home/frappe/frappe-bench/apps/erpnext`, so backend code runs from the
checked-out source while database, site state, and logs remain in Docker
volumes.

This is a development/self-hosted wrapper. Before production use, replace the
local default passwords, pin compatible database/image versions, configure
TLS and backups, and use an external persistent database/Redis setup.
