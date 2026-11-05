# PAYLOAD-LOGIX

PAYLOAD-LOGIX is a multi-agent system I built for changing a satellite payload configuration from natural-language requests. A local language model turns a request like "add a radio with mass below 0.5 kg and power below 3 W" into a structured command. A Payload Agent picks a component from a dataset, checks it against the satellite's limits in ordinary code, and saves it to a persistent blueprint. A Resource Allocation Agent (RAA), a Logistics Agent and a Risk Agent handle deadlines and failure recovery, and all four agents write their latest state to Redis.

Everything runs in one process on my machine, with no HTTP between agents. This README describes what runs today, how to run the demos, and what I have not built yet.

## Why I split it into agents

Ranking components by mass, power and volume does not tell me whether a part can arrive before the integration date, or whether a later change makes an earlier choice invalid. I gave each concern its own agent with a fixed message format, so one agent can notice a problem and send a typed message to the agent that has to fix it.

## Architecture

```
User / satellite designer
        │  natural-language request
        ▼
SLM Orchestrator ── routes on the command's `receiver` field
        │
        ├── PAYLOAD ──▶ Payload Agent
        ├── RAA ──────▶ RAA ──▶ Logistics Agent
        └── RISK ─────▶ Risk Agent (started with /risk start)

All four agents mirror their latest state to Redis.
The Risk Agent reads those mirrors and sends typed recovery messages.
```

| Component | What it does | How |
|---|---|---|
| **SLM Orchestrator** | Reads the request, extracts component, intent and constraints, routes it, returns the result | Qwen2.5-Coder-7B-Instruct-4bit via MLX |
| **Payload Agent** | Component selection, constraint checks, blueprint updates, recovery from interrupted operations | Qwen3-1.7B-MLX-4bit, CatBoost ranking, deterministic validation, SQLite |
| **RAA** | Schedules and cancels components with a deadline and priority, forwards each event to Logistics, ignores identical retries | Rule-based code |
| **Logistics Agent** | Receives schedule and cancel events from RAA and reports the outcome | Rule-based code |
| **Risk Agent** | Watches the other agents' state in Redis and sends typed recovery messages | Rule-based code |
| **Finance Agent** | Budget constraints on component choice | Planned, not built |

Both models run locally on Apple Silicon through MLX, so there is no external inference service. The language models only interpret requests. Mass, power and volume limits are checked in plain code, and a high ranking never overrides a failed check.

### Payload Agent

For each request, the Payload Agent:

1. Reads the structured command from the orchestrator.
2. Generates and ranks candidate components from the component dataset (CatBoost).
3. Checks the best candidate against the satellite limits in plain code.
4. Writes the result to the **blueprint**, the persistent record of the current payload configuration.
5. Returns a Protobuf result to the orchestrator.

Satellite limits (total mass, power, volume) are set in the console in plain language, for example "keep the satellite below 25 kg, 100 W and 50000 cm3", and stored in SQLite. The agent also keeps an **operation cache** with the last operation, so it can resume after an internal failure, a dropped message or a mismatch with another agent. The blueprint holds the current configuration, and the cache is only for recovery.

### RAA and Logistics

A schedule command names a component, a deadline in Unix seconds and a priority. The orchestrator sends it to the RAA, which records the schedule and forwards an event to Logistics. A cancel command works the same way and produces a cancel event. If the RAA receives the identical schedule command again, it prints its own message but does not forward a second event to Logistics.

The RAA deadline is the required date. Logistics does not redefine it. If Logistics can deliver earlier, that can change the order of operations (R1), but it does not change the deadline.

### Risk Agent

The Risk Agent does not compute a general risk score. It compares the state each agent last wrote to Redis and sends a typed message to the agent that has to act. It starts with `/risk start`, and it sends a message on its own when an agent's Redis state has not updated for more than three poll intervals.

Recovery codes:

| Code | Target | Meaning |
|---|---|---|
| **P1** | Payload | The selected component can no longer meet the delivery deadline. Reconsider it and pick an alternative. |
| **P2** | Payload | Internal failure, dropped message or subagent mismatch. Recover from the last saved operation. |
| **L1** | Logistics | Deadline conflict with the RAA, or the deadline cannot be met. |
| **L2** | Logistics | Failed to update the blueprint, or unresponsive. Reset or recover. |
| **R1** | RAA | Logistics reported a feasible earlier delivery, so the order of events may change. |
| **R2** | RAA | Unresponsive, or out of sync with the Payload Agent's blueprint. |

P1, L1 and R1 are about a decision that has become invalid. P2, L2 and R2 are about an agent that failed while executing. A recovery message does not prove the recovery worked, so each agent acknowledges it, and the agent's next state report shows whether the problem is gone.

The `/demo risk` command forces one P2 to Payload, one L1 to Logistics and one R1 to the RAA, so you can see each agent acknowledge its message.

## Data and ranking

- **Component dataset:** 961 component records from NASA's *State-of-the-Art of Small Spacecraft* 2026 data, with category, component name, manufacturer, mass, power and dimensions.
- **Synthetic data:** a Gaussian Copula baseline generates additional records that keep the relationships between attributes. Generated records are not guaranteed to be physically valid.
- **Ranking:** CatBoost orders the candidate components.
- **Retrieval:** keyword-based lexical retrieval over NASA source material, used by `/ask`. My notes call it CAG, but it is plain lexical retrieval and does not implement the full Cache-Augmented Generation method.
- **Custom datasets:** `/convert` loads a CSV of components, caches it, and lets the agent select from it instead of the NASA data. The CSV header is `component_id,category,manufacturer,mass_kg,power_w,dimension_x_cm,dimension_y_cm,dimension_z_cm`, and `tests/data/test_radios.csv` is an example.
- **Unknown values:** the model should not fill in missing specifications. Unknown values should be flagged for verification.

## Messages

Commands between the orchestrator and the agents are JSON. Agent results are Protobuf. A raw command to the RAA looks like this:

```json
{
  "receiver": "RAA",
  "intent": "SCHEDULE",
  "category": "PMAD",
  "component_id": "PMAD_017",
  "deadline_unix_sec": 1797177600,
  "priority": 2,
  "order_index": 1
}
```

The orchestrator produces commands like this from plain language. In `console_agents.py` you can also paste raw JSON of this shape and skip the model. Risk messages carry an error code (`P1`, `P2`, `L1`, `L2`, `R1`, `R2`), and agent results carry a success flag and an error code (`ERROR_NONE` on success).

## Running the demos

**Requirements:** an Apple Silicon Mac (MLX), the Python virtual environment in `venv/`, and Redis for the multi-agent demo. Loading the two local models takes about 10 seconds at startup.

<!-- Add installation steps here: creating the venv, installing requirements, downloading the two models, running the tests. -->

### Demo 1: payload agent (`console.py`)

```bash
cd MPR
venv/bin/python console.py
```

Wait for `PAYLOAD-LOGIX console (real agent). Type /quit to exit.`, then:

```
YOU> Keep the satellite below 25 kg, 100 W and 50000 cm3
YOU> Add a radio with mass below 0.5 kg and power below 3 W
YOU> /blueprint
YOU> /ask Which NASA SOA radios support S-band?
YOU> /quit
```

- The first command stores the limits in SQLite and prints `Satellite thresholds updated: ...`.
- The second prints the structured command, the agent's Protobuf result and a final answer, for example `A radio ... has been added ... RADIO_012`.
- `/blueprint` shows the current configuration, and `/ask` answers questions from the NASA data.

### Demo 2: custom component data (`console.py`)

```
YOU> /convert tests/data/test_radios.csv
YOU> Select a radio with mass below 0.4 kg, power below 2 W and volume below 100 cm3
YOU> Select a radio with mass below 0.6 kg, power below 3 W and volume below 200 cm3
YOU> Select a radio with mass below 0.05 kg
YOU> /datasets
YOU> /nasa
YOU> /quit
```

- `/convert` prints a summary (6 rows, 3 manufacturers, cached: yes). Converting the same file again reuses the cache without reparsing.
- The first selection returns `Selected Manufacturer C (RADIO_C2)`.
- The third selection returns `No valid candidate exists for those constraints.`
- `/nasa` switches back to the NASA dataset.

### Demo 3: multi-agent (`console_agents.py`)

Start Redis first, because the agents mirror their state there:

```bash
redis-server --daemonize yes      # if it is not already running
cd MPR
venv/bin/python console_agents.py
```

Schedule a component. The model reads the request, routes it to the RAA, and the RAA forwards it to Logistics:

```
YOU> Schedule the RADIO_C2 radio with deadline 1797004800, priority 1
CMD> {"category": "RADIO", "component_id": "RADIO_C2", "deadline_unix_sec": 1797004800, ...}
RAA-MSG>    {"action": "scheduled", "component_id": "RADIO_C2", ...}
RAA>        success=True error=ERROR_NONE
LOGISTICS-MSG> {"action": "ingested", "component_id": "RADIO_C2", "success": true, ...}
```

Variations:

```
YOU> Schedule PMAD_017 with deadline 1797091200
YOU> Cancel the RADIO_C2 radio
YOU> {"receiver":"RAA","intent":"SCHEDULE","category":"PMAD","component_id":"PMAD_017","deadline_unix_sec":1797177600,"priority":2,"order_index":1}
```

- The second schedule shows another `LOGISTICS-MSG>` for the new component and deadline.
- The cancel shows `RAA-MSG>` with `action: "cancelled"` and a cancel event from Logistics.
- The raw JSON skips the model. If you send the same schedule twice, the second run prints `RAA-MSG>` but does not forward to Logistics.

Risk Agent:

```
YOU> /risk start
YOU> /demo risk
YOU> /risk status
YOU> /risk stop
```

`/demo risk` sends one P2, one L1 and one R1 through the Risk Agent (`RISK-MSG>` lines), and each agent acknowledges. Without it, `RISK-MSG>` appears whenever an agent's Redis state goes stale for more than three poll intervals.

Status commands:

```
YOU> /agents       # last state of all four agents, from the Redis mirror
YOU> /blueprint
YOU> /datasets
YOU> /ask ...
```

`/agents` needs Redis running and says so if it is not. The wiring is in `console_agents.py`: the orchestrator routes by the command's `receiver` field, `PAYLOAD` to `PayloadAgent.handle_command`, `RAA` to `RaaAgent.handle_json` (which chains to Logistics), and `RISK` through `/risk start`. The payload path is the same as in `console.py`.

To stop Redis:

```bash
redis-cli shutdown
```

## Implementation status

| Component | Status |
|---|---|
| SLM orchestrator, local quantized inference | Implemented. Routes to Payload, RAA and Risk. |
| Payload Agent | Implemented |
| Component data cleaning, Gaussian Copula synthetic data, CatBoost ranking | Implemented |
| Deterministic validation against satellite limits | Implemented |
| SQLite state and blueprint management | Implemented |
| CSV import (`/convert`) with cache | Implemented |
| RAA (schedule, cancel, duplicate handling) | Implemented |
| Logistics Agent | Implemented as the receiver of RAA events |
| Risk Agent | Implemented. Starts on request, reacts to stale agent state, and can force P2, L1 and R1 for the demo. |
| Redis state mirrors | Implemented |
| Finance Agent | Planned |
| Kafka messaging | Planned |

## Testing

The test suite has 46 tests, and all passed at the last run. It covers P1 and P2 recovery, blueprint and operation-cache consistency when the process stops between the two writes, and duplicate, replayed, malformed and stale messages.

Not tested yet:

- Ranking quality against a baseline.
- Inference latency and memory use of the two local models.
- The case where a component ranks first and then becomes infeasible on delivery date, from Logistics reporting through P1 to a replacement in the blueprint.

## Limitations

- All agents run in one process. The message loss and ordering problems of a networked deployment are not exercised.
- The component data is public NASA survey data plus synthetic records. I have not checked it against manufacturer datasheets.
- Recovery has no retry limit, so I do not yet handle a recovery attempt that keeps failing.

## What I still need to do

- Build the Finance Agent and define how it affects component selection.
- Add Kafka for messaging between agents if I move them into separate services.
- Test the delivery-deadline case from Logistics through P1 to a replacement component.
- Measure ranking quality against a baseline, and the latency and memory use of the local models.
- Write the installation steps for the README.
