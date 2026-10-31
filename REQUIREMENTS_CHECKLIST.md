# SIS 3.3 superseding update
Simulation has been removed. Presentation uses live measurements and saved thresholds; see THRESHOLD_SETTINGS.md. Older simulation test notes below are historical validation, not current controls.

# SIS 3.2 update
Editable global thresholds are now available through Settings. See THRESHOLD_SETTINGS.md. This supersedes earlier fixed-threshold instructions below. Source files read saved threshold_settings.json on each cycle; historical records are unchanged.

# The SIS — requirements and evidence checklist

Basis: Embedded Systems Proxmox VE Python Monitoring Project Guide, sections10–14.
PostgreSQL is used instead of the optional SQLite prototype.

| Requirement | Implemented behavior | Evidence still needed on the laptop |
|---|---|---|
| Proxmox +3 Ubuntu nodes | Existing IDs101/102/103; sequential use allowed for8GB | Current configuration screenshots |
| CPU/RAM/root disk | psutil agent included; per-node cards/IPs/timestamps | Compare readings inside each guest |
| Independent health checks | Windows LIVE logger checks /health then validates /api/metrics | Actual agent/network test |
| Green/yellow/orange/red | Official defaults60/70/85 and60/75/90; fixed official limits | Save screenshot of each state |
| Three consecutive failures | RETRYING→UNAVAILABLE; three-failure limit | Actual Proxmox stop/start test |
| Event timing | first_failure_at,last_seen,recovery_at,last_outage_at | Actual outage/recovery screenshot |
| PostgreSQL history | readings,events,alerts,node_state; atomic writes and deduplicated transitions | Current production sample/schema export |
| Minimum fields | Metrics table/export hasID,node,metric,value,severity,status,event timestamp | Export at least one CSV |
| CSV headers/time/source | Four source-filtered exports;UTC, source labels | Attach actual exported files |
| Restart persistence | systemd agent;settings JSON;DB state restores | Actual guest reboot/service check |
| Warning/critical alarms | Distinct funny clips,volume,silence,notification inbox;offline sound suppressed | Listen on actual laptop speakers |
| Adjustable demo inputs | Confirmed per-VM percentages +simulated failure;header Demo button;fixed thresholds | Run Demo guide;capture results |
| Architecture/IP table | Architecture.svg and IP table included | Include the supplied diagram in final report |
| Host virtualization evidence | Nested lab already configured | Host specs/KVM screenshots |
| Technical report | Design,implementation,limitations described inREADME/guide | Final report/conclusion and group presentation |

## Architecture
Windows laptop → VirtualBox Proxmox-Lab → Proxmox host → Ubuntu VM101/102/103.
Windows logger → guest/health and/api/metrics → PostgreSQL → Waitress/Flask dashboard.
Browser per-VM demo inputs → atomicJSON → same running logger → SIMULATED PostgreSQL records/alarms.
Browser sound/inbox are dashboard outputs; database events are the retained history.

| System | Address | Service |
|---|---|---|
| Windows host-only |192.168.56.1| Logger/viewer/PostgreSQL run on Windows |
| Proxmox |192.168.56.10| HTTPS8006 |
| VM101 monitor-node1 |192.168.56.21| HTTP5123 |
| VM102 monitor-node2 |192.168.56.22| HTTP5123 |
| VM103 monitor-node3 |192.168.56.23| HTTP5123 |
| The SIS viewer |127.0.0.1| HTTP5124 |
| PostgreSQL |127.0.0.1| TCP5432 |

The controlled demo does not replace evidence of actual guest shutdown/reboot.
Software tests do not establish 100% operation of an unobserved Windows installation.
