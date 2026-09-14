# letron_api

Technical Frappe app used by the Letron ERPNext workspace.

This app intentionally contains no business DocTypes or business workflow.
ERPNext/Frappe native controllers, permissions and database remain the business
execution engine and runtime source of truth.

`letron_api` provides only the integration and control boundary:

- curated `/api/v1` route mapping and native lifecycle actions;
- health/runtime readiness;
- durable delivery outbox integration;
- `config.yaml` and `policy.yaml` validation, reconcile and drift detection;
- fixed-path System Manager API for editing those two bind-mounted YAML files;
- single-site Holding bootstrap with a Company Group and legal Companies using
  ERPNext's native Standard Chart of Accounts and country fixtures.

It does not define a parallel policy language, generic resource fallback,
shadow business records or an alternative ERPNext workflow engine.

The public business contract remains five modules, 23 resources and 137
operations. The separate typed control-plane contract exposes only fixed-path
GET/PUT operations for `config.yaml` and `policy.yaml`; it is not counted as
business API surface.

The current policy bundle manages Company bootstrap plus 69 declared native
ERPNext policy documents, including the current/comparative Fiscal Years,
Finance Book, statutory tax masters and Company-scoped Cost Center records. It
must not be described as complete coverage of every ERPNext setting. Exact
source classifications and implementation gaps are recorded in
[`Configuration_Inventory.md`](../../docs/Configuration_Inventory.md), and the
handoff verdict is recorded in [`ERP_PRD.md`](../../docs/ERP_PRD.md).
