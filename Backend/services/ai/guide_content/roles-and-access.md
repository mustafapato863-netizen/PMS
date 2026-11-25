# User Roles, Regions, and Access Guide

## User Roles and Access Scope (RBAC)

PMS enforces strict server-side Role-Based Access Control (**RBAC**) across every dashboard, export, and AI Assistant query so users only view authorized scopes:

- **Admin**: Unrestricted access across all regions, branches, functions, and levels, plus User Management, Data Uploads, and Monthly Evaluation Settings (`Save → Preview → Approve → Apply`).
- **General Manager / Executive / Performance Team**: Broad leadership visibility across authorized company scope; General Managers and Performance Team members can also manage corrective actions.
- **Regional Manager / Branch Director / Function Director**: Automatically locked to their assigned region (`EGY` or `UAE`), UAE branch (`Dubai`, `Sharjah`, `Ajman`, `Clinics`), or parent function.
- **Manager**: Scoped to assigned team(s) with permission to create and update corrective actions for their teams.
- **Viewer / Function Viewer**: Read-only analytical access within assigned scope (cannot create or modify corrective actions).
- **Employee**: Self-only access restricted strictly to their own 360 Employee Scorecard, KPI trends, and assigned actions.

## Regions and UAE Branch Filtering

PMS organizes performance across two regions and four UAE branches:

- **Regions**: **Offshore Egypt (`EGY`)**, **UAE Region (`UAE`)**, and **All regions** (combined view with a Region Performance Share comparison).
- **UAE Branches**: **Dubai**, **Sharjah**, **Ajman**, and **Clinics**.
- **Branch Filtering**: Selecting a UAE branch in **Monthly Review**, **Executive Summary**, or **Team Dashboard** filters branch-owned teams (such as UAE Pre-Approvals and clinical units) and recalculates geo-partitioned Call Center (**Inbound** and **Outbound**) Attendance Rate and weighted scores specifically for that branch.
