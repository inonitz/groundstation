# Track 1 tracker — decisions and open items (2026-09-10)

Companion to docs/active/2026-09-10-track1-tracker-handoff.md.
This file records the owner's rulings as they land. Chat is lost; this file is not.
Update items in place: move an item from "Open" to "Settled" when the owner rules.

## Settled decisions
- Install path: tools/tracker/ for now. The tracker must later become its own separate
  project/repo. It stays a self-contained logical unit. Build it self-contained from day one.
  (Owner, 2026-09-10.)
- No data import. The team starts from scratch. It fills in current progress, future research
  topics, and future features by hand. (Owner, 2026-09-10.)
- Access model: VPN. The team is fully remote. There is no shared LAN and no office.
  Every member connects over a VPN. The tracker is never exposed to the public internet.
  (Owner, 2026-09-10.)
- Wiki location: research write-ups live in the tracker wiki. The backup below protects them.
  (Owner, 2026-09-10.)
- Deliverables (simplified per owner): three scripts the owner runs by hand.
  1. install: set up Docker, then install and start OpenProject.
  2. backup: dump the database and attachments, then push the archive to a private git repo
     and/or copy it to another PC.
  3. restore: rebuild the tracker from a backup archive.
  An optional seed script can create the topic/subproject skeleton (handoff section 5).
- Constraints (from the handoff): self-hosted, free, no per-seat cost, owner-controlled.
  NOT Plane. Not on the 8 GB demo laptop.

## Open decisions (owner to rule)
- Tool: OpenProject Community (recommended, working choice) or Redmine (fully free, older UI).
- Host: a repurposed always-on machine at the owner's home (owner's lean, best privacy) or a
  small VPS (~$4-5/month, better uptime, but the provider holds the disk).
- VPN tool: Tailscale (easiest, free for up to 6 users, no router setup) or WireGuard
  (fully self-hosted, no third party, more setup on the host).
- Seed: the agent seeds the topic/subproject skeleton, or the owner fills everything.

## Verified facts (checked 2026-09-10)
### OpenProject data and privacy
- Self-hosted Community keeps all project data on your host: a PostgreSQL database plus file
  attachments. The data never leaves your machine.
- OpenProject Community is open source (GPLv3). It is not a hosted service. It does not send
  your project content to OpenProject or any third party.
- A version check may ping OpenProject for updates. It sends no project content. It can be off.
- On a VPS, the provider physically holds the disk. For maximum privacy, host on your own
  machine, or encrypt the disk.

### OpenProject: free Community vs paid Enterprise
Source: https://www.openproject.org/pricing/
- Free (Community): kanban board, wiki, work packages, Gantt, subprojects, time tracking,
  custom fields, two-factor auth, LDAP, limited baseline comparison.
- Paid (Enterprise): team planner, cross-subproject boards, advanced baseline comparison,
  SSO/SAML, enhanced reporting graphs, BIM, professional support.
- The four stated needs are all covered by the free edition.

### VPN free tiers
Source: https://tailscale.com/pricing (checked 2026-09-10).
- Tailscale free Personal plan: up to 6 users, unlimited devices. The 4-person team fits.
- Tailscale carries connection setup only. The tracker data does not pass through Tailscale.
- WireGuard is free with no user cap and no third party. It needs more setup on the host.

### VPS pricing
- Hetzner CX22 (x86, 2 vCPU, 4 GB, 40 GB): ~$4.59/month.
- Hetzner CAX11 (ARM, 2 vCPU, 4 GB): ~$3.79/month.
- Redmine needs less RAM and costs less.

### Linear (SaaS alternative) — privacy and paywall (checked 2026-09-11)
Sources: linear.app/security, /privacy, /dpa, /pricing.
- Privacy guarantees: TLS 1.2 in transit, AES-256 at rest; SOC 2 Type II; ISO 27001:2022;
  GDPR with Standard Contractual Clauses; HIPAA BAA available; EU-or-US region chosen at
  workspace creation; deletion on account close, certified on request.
- Subprocessors (another company Linear hands data to) include AWS, Google, Cloudflare (infra)
  and Anthropic, OpenAI, Cohere, Fireworks (AI). 30 days' notice before a new one.
- Privacy gap: the public DPA has NO explicit "we do not train AI on your content" clause. A hard
  no-training guarantee needs Linear's written AI terms, or self-hosting. Data lives on Linear's
  cloud; certifications are promises, not physical control.
- Paywall: Free caps at 250 issues and 2 teams. Unlimited issues needs Basic ($10/user/month);
  unlimited teams, guests, private teams need Business ($16/user/month); SAML/SCIM/IP/audit are
  Enterprise. For a 4-person team the only paywall that bites is the 250-issue cap. Topics map to
  Projects (unlimited in a team), not Teams, so the 2-team cap likely does not bite.
- Contradiction: removing the issue cap is per-seat billing, the model the owner rejected.

### Non-self-host options + new requirement (checked 2026-09-11)
- NEW requirement (owner, 2026-09-11): the tracker serves non-developer engineers too, not only
  coders, and should keep GitHub state in sync. This demotes dev-centric git platforms
  (GitHub Projects, GitLab, Codeberg): non-coders resist a repo-shaped UI.
- ClickUp Free Forever: no seat cap, unlimited members and tasks, $0. Contracts forbid AI vendors
  from training on or retaining customer data, on all plans. Non-dev friendly. GitHub integration.
  Catches: 60 MB storage, 100 automations/month, limited Gantt/dashboards; still US SaaS cloud.
  Sources: clickup.com/security, help.clickup.com AI FAQ, usecarly free-plan limits.
- Notion Free: contractual no-training on all plans, non-dev friendly, GitHub sync via integration.
  Catches: free-plan AI vendor may retain data 30 days; pages shared with OpenAI/Anthropic when AI
  used; US cloud. Source: notion.com/help/ai-safety.
- GitHub: private repo content at rest is not trained on; but Copilot interaction data trains by
  default for individual Free/Pro from 2026-04-24 unless opted out (Business/Enterprise excluded);
  dev-centric.
- Verdict: on the owner's two Linear objections (per-seat + AI training), ClickUp Free clears both
  and fits a mixed team. The residual only self-hosting removes: data on a vendor's cloud.
  GitHub sync is available on every option here, including self-hosted OpenProject.
