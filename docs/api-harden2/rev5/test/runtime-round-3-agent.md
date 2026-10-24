# runtime (rev5), round 3: the manager agent's answer (2026-10-16)

All eight findings are accepted and applied.
- **R3-1** on_exit takes the launch lock first; once stopping is set it returns and leaves the
  pidfd to Die; the lock list names the pidfd close.
- **R3-2** The quit sets the stopping flag under the lock and drops pending relaunches; the
  second SIGINT goes by stop-sent time, whoever sent the first; a test.
- **R3-3** The launch lock is open point 6, in the MOD2 form; the agent decides nothing on SK4.
- **R3-4** The six stale lines fixed; the greps are clean.
- **R3-5** The two adapters are written out in instance 1; the telemetry one clamps at zero.
- **R3-6** A ledger line for the perf.h comment (PRF6); the carried item says "in parallel".
- **R3-7** Both items carried to the app step in modules/README.md.
- **R3-8** Open point 1 asks only what the key means; the quit's airborne behaviour is the
  app step's.
Answers: 1. yes, open point 6. 2. the runtime entry writes it, as PRF6 beside TEL19.
No round 4.
