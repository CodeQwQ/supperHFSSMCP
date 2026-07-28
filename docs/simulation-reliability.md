# Simulation Reliability

## Long-running jobs

`run_simulation(setup_name)` first performs the evidence-bearing `validate_design` gate. It then creates and persists a job record and submits the real backend solve to the service simulation worker. The MCP request returns a job id and does not keep the HTTP request open for the lifetime of the HFSS solve. A disconnected client can reconnect and call `get_simulation_job(job_id)` while the same service continues polling AEDT.

The PyAEDT backend starts `analyze_setup(name=..., blocking=False)` and polls `are_there_simulations_running` or `oDesktop.AreThereSimulationsRunning()`. The simulation worker uses an unlimited backend wait; the old 300-second worker deadline is only for ordinary bounded commands and is never applied to the real solve. `release_connection` is rejected while a queued or running job exists, so releasing control cannot silently kill the solver worker.

## Immediate solver errors

Before submission, the backend records the current HFSS message baseline. Every status poll reads AEDT/PyAEDT messages again and compares new messages against that baseline. Messages containing `error`, `failed`, or `invalid`, including `Sweep Sweep1 failed` and `process hf3d exited with code 259`, immediately mark the job as `failed`. The job retains `failure_reason`, `result.hfss_messages`, and `solver_state_observations`; result extraction is not responsible for discovering solver failure.

If the AEDT status API is unavailable, the backend returns a controlled failure because completion cannot be proven. It never reports `completed` merely because no running state could be read.

## Recovery contract

`simulation_jobs.json` is written atomically after each job state transition. A new service instance can recover completed or failed records by job id. A live MCP session timeout does not stop the service worker; the client should reconnect to the same MCP service and poll the saved job id. A running solve must finish or fail before the HFSS connection is released.

## Acceptance

The required acceptance uses an independent sub-agent and a real MCP client connected to Ansys Electronics Desktop Student 2025 R2. It must prove:

1. `validate_design` executes before `run_simulation`.
2. HFSS visibly enters a real solver run.
3. A solver failure is present in the simulation job immediately, before S-parameter extraction.
4. A client reconnect can query the same job id.
5. Release is blocked during a live solve and succeeds after completion or failure.
