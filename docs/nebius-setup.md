# Nebius AI Cloud connection

Connected and verified on 12 September 2026.

| Setting | Verified value |
|---|---|
| Service | Nebius AI Cloud, `console.nebius.com` |
| Local environment | Existing Ubuntu distribution under WSL 2 |
| CLI | Official Nebius CLI 0.12.275, Linux AMD64 |
| CLI executable | `/home/wsl/.nebius/bin/nebius` on this machine |
| Profile | `driftops`, activated as the CLI default |
| Authentication | Nebius browser sign-in flow |
| Project | `default-project-eu-north1` |
| Region | `eu-north1`, selected to match the tenant's region |

Installation used the installer linked by the [official CLI documentation](https://docs.nebius.com/cli/install). The installer was downloaded and inspected before execution. Authentication used the [official browser authorization flow](https://docs.nebius.com/cli/no-browser). CLI authentication state remains inside the WSL user environment, outside the repository. Local installer downloads and credential-file patterns are excluded by `.gitignore`.

Verification completed successfully: CLI version, active profile, authenticated identity request, tenant/project listing, and compute instance listing in the selected project. Its compute inventory was empty. No VM, disk, cluster, service account, or API key was created during connection setup. GPU quota was subsequently verified as recorded below; capacity and remaining credits are still unverified.

From this repository in PowerShell:

```powershell
.\scripts\nebius.ps1 version
.\scripts\nebius.ps1 compute instance list --format json
```

The launcher discovers the current Ubuntu user's home and always selects the `driftops` profile. It forwards arguments directly to the installed CLI. An equivalent direct command on this machine is:

```powershell
wsl --distribution Ubuntu --exec /home/wsl/.nebius/bin/nebius --profile driftops compute instance list --format json
```

If browser authentication expires, use the CLI's normal sign-in flow. Do not print access tokens into a shared terminal transcript or commit authentication files.

Nebius supplies access to cloud infrastructure. The user confirmed the team's actual voucher is **$600**, superseding the hosts' general $1,000 announcement. Remaining balance and instance availability still need checking before training resource setup. Extra credits may be requested if needed, after discussing the need with the user.

Read-only readiness checks on 12 September 2026 found no existing compute instances and tenant quota of 32 each for H100, H200, and L40S GPUs in `eu-north1`. Quota is an allowance, not proof of current capacity. No paid resource or training run has started.

Before every training run, give the user an overview of its objective, necessity, data/splits, trainable components, hardware, expected cost, stopping conditions, evaluation, and outputs, as required in the [implementation plan](implementation-plan.md).

OpenTSLM temporal and base-model weights are separate access dependencies. The required path is to fine-tune a TSLM and export a reloadable checkpoint or learned adapter. An Aionic inference endpoint may help if supplied, but self-hosted training/inference can proceed once weights and compute are available; cloud authentication alone does not establish either.
