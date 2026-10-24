# PAYLOAD-LOGIX: Complete System Design

End-to-end architecture, agent responsibilities, communication protocol, data-flow, recovery mechanisms, and implementation boundaries.

PAYLOAD-LOGIX is an AI-assisted, multi-agent system designed to support satellite payload integration and resource allocation. Its central idea is to coordinate specialized agents through explicit communication contracts so that component selection, logistics, resource allocation, and risk management can work together instead of operating as isolated modules.

The design combines small language models (SLMs), structured inter-agent messages, deterministic validation, component-ranking methods, persistent state, and risk-triggered recovery.

One important distinction throughout this document: this describes the architecture and protocol you designed, using the details available in our conversation. Where a mechanism is implemented, planned, or only specified at the protocol level, I distinguish those states rather than treating the entire envisioned system as already operational.

## 1. System overview

User / Satellite Designer

Requests a payload change, component addition/removal, or configuration update.

SLM Orchestrator

Interprets the request, structures it, and routes the task to the appropriate agent.

Custom JSON / Protobuf communication contracts

Payload Agent

Component selection, blueprint management, validation and recovery.

Logistics Agent

Manufacturer delivery information and delivery feasibility.

RAA

Resource allocation and expected deadline constraints.

Risk Agent

Monitors reported state and signals corrective action.

Finance Agent — planned

Intended to introduce financial constraints into component and procurement decisions.

Supporting infrastructure: local state and blueprint persistence, component data and ranking, retrieval, deterministic validation, and a proposed Redis/Kafka integration layer.

The key design principle is separation of responsibilities with a shared communication contract. Each agent can focus on its own domain, while the orchestrator and protocol define how the overall workflow fits together.

The diagram is a conceptual view of the intended system. It does not imply that every agent or infrastructure component has been implemented or integrated.

## 2. The SLM Orchestrator

The orchestrator is the system's entry point and coordination layer.

### Model and role

The design uses Qwen2.5-Coder-7B-Instruct-4bit through MLX as the orchestrator model. Its purpose is to translate a user's natural-language request into a structured instruction that the relevant agent can process.

For example, a user might request:

> Add a radio to the satellite payload, subject to the mass and power constraints, and ensure it can be delivered before the integration deadline.

The orchestrator's intended responsibilities are:

1. Interpret the request and identify the user's intended operation.
2. Extract the relevant component, intent, and constraints.
3. Convert the request into the project's structured data contract.
4. Route the request to the responsible agent.
5. Receive the outcome from that agent.
6. Return a success or failure result to the user.

### Why use an SLM?

A small language model can run locally, which is useful for controlling deployment costs and avoiding dependence on an external inference service. It also makes it possible to use a natural-language interface while keeping the downstream operations structured.

The SLM should not be treated as the ultimate authority for hard engineering constraints. Those constraints should be enforced by deterministic validation and the responsible domain agents.

Implementation boundary: The orchestrator and its model are part of the described implementation. The current project notes indicate that routing is focused on the Payload Agent, rather than all planned agents operating as a fully integrated system.

## 3. Payload Agent

The Payload Agent is the central domain agent in the currently implemented vertical slice. It is responsible for translating a component-related instruction into a proposed payload modification and maintaining a consistent payload blueprint.

### Model and supporting components

The design uses Qwen3-1.7B-MLX-4bit for payload-related reasoning, alongside conventional software components.

Structured instruction from orchestrator

Payload reasoning

Interprets the requested component operation and relevant component information.

Candidate generation and ranking

Uses component data and CatBoost-based candidate ranking to support component selection.

Deterministic validation

Checks the proposed modification against applicable constraints using conventional code.

SQLite / local state

Supports local state management.

Persistent blueprint

Maintains the current payload configuration.

The diagram represents the logical processing flow, not necessarily a verified execution trace for every component.

### 3.1 Component selection

The Payload Agent uses component information such as:

- Component name and category.
- Mass.
- Power consumption.
- Dimensions or volume, depending on the component data.
- Relevant compatibility and payload constraints.
- Candidate-ranking output.

The project's component dataset is derived from NASA's State-of-the-Art of Small Spacecraft 2026 data. A Gaussian Copula-based synthetic-data process and CatBoost ranking are also part of the described technical stack.

The model can assist with interpreting component information, but it should not invent missing engineering specifications. Uncertain values should be flagged for verification rather than silently treated as correct.

### 3.2 Blueprint management

The blueprint represents the current payload configuration.

When a component is added, removed, or updated, the intended workflow is to validate the change and persist the resulting configuration. The blueprint is meant to remain the authoritative representation of the current design, rather than being merely a transient model response.

### 3.3 Cache and operation recovery

Your protocol specifies a local cache that stores the last operation and a persistent blueprint that is updated as the configuration changes.

This distinction is important:

- The blueprint represents the longer-lived configuration state.
- The operation cache supports recovery from interrupted processing.

The intended P2 recovery path allows Payload to resume from its last saved operation when an internal failure, packet drop, or subagent mismatch occurs.

For a robust implementation, the cache should also track operation identity and completion status. Otherwise, replaying an operation after an uncertain acknowledgement could add or remove the same component twice.

### 3.4 Payload Agent's protocol responsibilities

The Payload Agent needs to support two broad classes of incoming messages:

1. SLM-originated instructions: component addition/removal requests, with relevant attributes.
2. Risk-originated recovery messages: P1 to reconsider an affected component, or P2 to recover from an execution or consistency failure.

It sends a success/failure result back to the SLM and supplies state information to Risk.

Implementation status: Payload reasoning, component-ranking infrastructure, local state and recovery-related code are part of the described implementation. The precise extent of fully integrated P1/P2 behavior should be confirmed through end-to-end tests.

## 4. Logistics Agent

The Logistics Agent is intended to manage whether a selected component can be delivered in time for the satellite integration schedule.

It addresses a constraint that component ranking alone cannot resolve: a technically suitable component is not useful if it cannot arrive when required.

### Responsibilities

- Receive component-related requests and delivery constraints.
- Track manufacturer delivery information.
- Determine or report whether the expected delivery can meet the required deadline.
- Communicate deadline information to the relevant agents.
- Respond to Risk messages when logistics state is inconsistent or the agent needs recovery.

### Communication example

An instruction sent from the SLM to Logistics may contain:

- `Receiver = Logistics`
- `Sender = SLM`
- `Intent = Add`
- `Component = Radio`
- `Deadline = 7_10_27`

In your specification, the date represents 7 October 2027 in `dd_mm_yy` format. Manufacturer-side information is expected to supply the delivery date; if it is missing, the component may remain in a waiting state.

The deadline format is currently conceptual. A production schema should use an unambiguous date representation and define what happens when the date is missing or invalid.

### L1 and L2 recovery

- L1: Signals a logistics/RAA deadline or synchronization problem. The logistics deadline must respect the relevant RAA constraint.
- L2: Signals that Logistics has failed to update the blueprint or is unresponsive, prompting a reset or recovery action.

The intended Risk-to-Logistics message includes an error code and, for L1, the affected component and deadline.

Implementation status: Logistics is described as protocol-level or planned, rather than a fully running, independently validated agent.

## 5. Resource Allocation Agent (RAA)

The Resource Allocation Agent is intended to coordinate resource requirements and the deadlines imposed on satellite integration.

Its purpose is broader than selecting an individual component. It should help ensure that the overall configuration and its schedule remain feasible.

### Responsibilities

- Maintain or communicate expected deadlines for components.
- Supply scheduling constraints to Logistics.
- Receive feasible delivery proposals from Logistics.
- Notify the coordination system when event ordering or scheduling needs to change.
- Detect or recover from state inconsistencies involving the payload blueprint.

### Deadline relationship

Your intended design distinguishes between:

- The deadline appointed by RAA for a component.
- The delivery deadline or expected delivery date reported by Logistics.

Logistics may be able to deliver earlier than the RAA deadline. It must not silently redefine the RAA's required deadline; instead, the earlier delivery may allow the system to change the order of operations.

### R1 and R2 recovery

- R1: Signals that Logistics has proposed a feasible earlier delivery and that the order of events may need to change.
- R2: Signals that RAA is unresponsive or out of sync with the Payload Agent's blueprint and needs recovery.

The RAA-to-Risk message is intended to report the last relevant component and expected deadline.

Implementation status: RAA is described as designed or protocol-level. Its full scheduling logic and integrated behavior have not been established by the information available here.

## 6. Risk Agent

The Risk Agent is arguably the most distinctive coordination component in your architecture.

Rather than being limited to producing a general risk score, its intended role is to monitor messages and state reported by other agents, identify specified inconsistencies or constraint violations, and send targeted recovery signals.

### Inputs to Risk

Your protocol defines three outgoing-to-Risk message types:

| Sender    | Information supplied                                |
| --------- | --------------------------------------------------- |
| Payload   | Last relevant component and manufacturer            |
| Logistics | Last relevant component, manufacturer, and deadline |
| RAA       | Last relevant component and expected deadline       |

Risk can use these reports to reason about discrepancies in component state, delivery commitments, and resource-allocation deadlines.

For example, Logistics may report that a component will arrive after the deadline imposed by RAA. Risk can then send a P1 signal to Payload, asking it to reconsider the affected component.

### Error-code design

Your protocol defines six agent-specific recovery codes.

## Payload recovery

P1

Decision invalidation

The selected component can no longer satisfy the logistics deadline. Payload should reconsider its selection and choose an alternative that satisfies the applicable constraints.

P2

Execution or state recovery

An internal failure, packet drop, or mismatch between subagents requires recovery from the last consistent operation.

## Logistics recovery

L1

Deadline conflict

Logistics is out of sync with RAA or cannot meet the required deadline.

L2

Agent recovery

Logistics fails to update the blueprint or becomes unresponsive.

## RAA recovery

R1

Schedule reordering

A feasible earlier delivery from Logistics may justify changing the order of events.

R2

Agent recovery

RAA becomes unresponsive or its state becomes inconsistent with the payload blueprint.

The important architectural distinction is that the codes encode different reasons for intervention, not simply a generic failure flag.

### How Risk should operate

The intended control flow is:

1. Receive agent status and deadline information.
2. Identify a relevant discrepancy or violation.
3. Determine which agent is responsible for correcting it.
4. Send the appropriate typed error message.
5. Allow the receiving agent to recover, replan, or report failure.
6. Receive a subsequent status update to establish whether the problem was resolved.

The last step is an important engineering requirement for a complete implementation. Sending a recovery message does not itself prove that recovery succeeded.

Implementation status: Risk message formats and Payload-side recovery handlers are described in the project notes. A fully running Risk Agent that continuously monitors every agent has not been established as implemented.

## 7. Finance Agent

The Finance Agent is part of the broader intended architecture.

Its prospective role is to introduce budget and procurement constraints into component integration. For example, a component could satisfy technical and delivery requirements but exceed the available budget.

Potential responsibilities include:

- Maintaining component or procurement cost information.
- Comparing component options against budget constraints.
- Reporting financial infeasibility.
- Supplying financial constraints to the orchestration or decision process.

However, the details of its message types, optimization logic, and integration with the other agents have not been specified sufficiently in the information available here.

Therefore, Finance should be presented as a planned extension, not a completed subsystem.

## 8. Custom inter-agent communication protocol

Your handwritten specification defines the intended communication contract between the agents. The project uses a structured JSON/Protobuf approach, with messages identifying the receiver, sender, intent, component, relevant attributes, deadlines, or recovery codes as appropriate.

The key idea is that each message is tailored to a particular interaction.

### 8.1 SLM to Payload: component modification

For a Radio addition, your conceptual message is:

```

{
  "Receiver": "Payload",
  "Sender": "SLM",
  "Component": "Radio",
  "Intent": "Add",
  "Mass": "200",
  "Power": "2",
  "Dimensions": "120"
}

```

Your specification describes mass in grams for Radio, power in watts where parseable, and dimensions as volume in cm³. The values above are illustrative protocol values, not verified specifications for an actual radio.

For the High Heritage Miniature Reaction Wheels component, the message uses the component identifier `HHMRW`. For PMAD, the example uses `PMAD` and the field `Volume` rather than `Dimensions`.

These examples show that your protocol was designed around the attributes relevant to the component category, rather than assuming every component has exactly the same metadata.

There are, however, schema decisions to resolve:

- Mass is specified in grams for Radio and kilograms for other examples.
- `Dimensions` and `Volume` appear to represent related but inconsistently named concepts.
- Power and volume may be unavailable or unused by the ranking model for some components.
- Missing, unknown, and invalid values need distinct handling.

A canonical schema should define units and types consistently, even if component-specific validation rules differ.

### 8.2 SLM to Logistics: delivery request

```

{
  "Receiver": "Logistics",
  "Sender": "SLM",
  "Intent": "Add",
  "Component": "Radio",
  "Deadline": "7_10_27"
}

```

This message expresses the component-related operation alongside a deadline constraint. The manufacturer's expected delivery date is intended to come from the manufacturer side of the workflow.

### 8.3 Risk to Payload: recovery instruction

```

{
  "Receiver": "Payload",
  "Sender": "Risk",
  "ErrorCode": "P1",
  "Component": "Radio"
}

```

For P1, the component identifies the item that needs reconsideration. In your specification, P2 does not require a component field because the failure may concern the Payload Agent's execution or internal state rather than one particular component.

### 8.4 Risk to Logistics

```

{
  "Receiver": "Logistics",
  "Sender": "Risk",
  "ErrorCode": "L1",
  "Component": "Radio",
  "Deadline": "dd_mm_yy"
}

```

The component and deadline are relevant to L1. L2 is intended to signal recovery without requiring the same component-specific fields.

### 8.5 Risk to RAA

```

{
  "Receiver": "RAA",
  "Sender": "Risk",
  "ErrorCode": "R1",
  "Component": "Radio",
  "Deadline": "dd_mm_yy"
}

```

The deadline in R1 is intended to communicate a feasible delivery date reported by Logistics, potentially allowing the event sequence to be revised.

### 8.6 Agents to Risk

Your protocol defines status reports from Payload, Logistics, and RAA.

Payload reports the last relevant component and manufacturer. Logistics also reports the deadline. RAA reports its last relevant component and expected deadline.

These messages give Risk a common basis for examining the reported state across agents.

Two sender/receiver values in your handwritten RAA examples appear to be copy errors: the RAA-to-Risk message lists Logistics as the sender, and the Risk-to-RAA message lists Logistics as the receiver. The canonical schema should correct those values.

### 8.7 Agents to SLM: result messages

For Payload, your result message is conceptually:

```

{
  "Receiver": "SLM",
  "Sender": "Payload",
  "Success": "1/0",
  "ErrorCode": "P1"
}

```

Equivalent result messages are specified for Logistics and RAA, using `L1` and `R1` respectively as examples of error codes.

The intended meaning is:

- Success = 1: the requested operation was completed successfully.
- Success = 0: the operation failed, with an error code supplied when applicable.

In an actual Protobuf schema, `Success` should be a boolean rather than the string `"1/0"`. Error-code presence and allowed values should also be validated.

### 8.8 Recommended additions for a robust protocol

Your existing fields define the basic message semantics. For reliable integration, I'd add:

| Field                | Purpose                                                           |
| -------------------- | ----------------------------------------------------------------- |
| `protocol_version`   | Identifies the schema version                                     |
| `message_id`         | Uniquely identifies a message                                     |
| `correlation_id`     | Links related messages in one workflow                            |
| `operation_id`       | Prevents duplicate execution of the same operation                |
| `blueprint_revision` | Identifies the blueprint state on which a decision was based      |
| `status`             | Distinguishes accepted, running, completed, and failed operations |
| `timestamp`          | Records when the message was created                              |
| `retryable`          | Indicates whether retrying is appropriate                         |

These are proposed improvements, not fields established in your original handwritten protocol.

## 9. Data pipeline, retrieval, and candidate ranking

The architecture is not based on language-model reasoning alone. It combines a component dataset, retrieval, synthetic data generation, ranking, and deterministic checks.

### 9.1 Component dataset

The project uses a cleaned dataset derived from NASA's SOA-2026 component information. The recorded dataset contains 961 component records, with standardized fields such as:

- Category.
- Component name.
- Manufacturer.
- Mass.
- Power.
- Dimensions.

This provides structured information for component selection and candidate generation.

### 9.2 Synthetic data generation

The project uses a Gaussian Copula-based baseline to generate synthetic data based on the component dataset.

The intended purpose is to augment the available data while modelling relationships between attributes. Synthetic data can increase the amount of material available for experimentation, but it does not automatically guarantee that generated component specifications are physically valid. Validation against real-world constraints remains necessary.

### 9.3 Candidate ranking

CatBoost ranking is used to help rank component candidates. This provides a conventional machine-learning component within the broader AI architecture.

The intended division of responsibility is:

- The language model interprets the requested modification.
- Structured data supplies candidate component information.
- The ranking model orders candidate options.
- Deterministic validation checks whether the proposed choice satisfies the applicable hard constraints.

This is a useful hybrid design because a high ranking should not override a hard engineering constraint.

### 9.4 Retrieval and context

The project includes a lexical retrieval mechanism referred to as CAG in the project notes. It uses keyword-based retrieval of relevant source material to support reasoning.

It should be described accurately as lexical retrieval in the current implementation, rather than assuming that it implements every mechanism from the original Cache-Augmented Generation research.

### 9.5 Local inference

The project uses MLX-based quantized models on Apple Silicon:

- Qwen2.5-Coder-7B-Instruct-4bit for orchestration.
- Qwen3-1.7B-MLX-4bit for payload reasoning.

The use of local models is relevant to cost, deployment independence, and resource constraints. Actual performance should be established with measured latency, memory use, and task-quality tests rather than inferred from model size alone.

## 10. State management and supporting infrastructure

### SQLite and local state

SQLite is part of the described implementation and supports local state management. The Payload Agent's cache and persistent blueprint serve different purposes: one helps with operation recovery, while the other maintains the current payload configuration.

A robust design should specify which store is authoritative, how state changes are committed, and what happens if a process stops between updating the cache and saving the blueprint.

### Redis and Kafka

Redis and Kafka are part of the broader planned infrastructure.

Their intended roles could include:

- Redis: fast access to shared or temporary state, caching, or coordination data.
- Kafka: asynchronous event delivery between agents and other system components.

These technologies can be useful if the system evolves toward independently running services. However, their presence in the architecture should not be represented as a completed integration unless the corresponding implementation and tests exist.

### Why separate these layers?

The system has three different concerns:

1. Reasoning: interpreting requests and proposing actions.
2. Domain execution: validating, ranking, scheduling, or managing delivery.
3. Coordination and persistence: exchanging messages and maintaining consistent state.

Keeping these concerns separate makes the system easier to test and evolve. It also helps identify which component is responsible when something goes wrong.

## 11. End-to-end workflow

Consider a user requesting the addition of a Radio to a satellite payload.

Step 1 — Request interpretation

The user describes the desired payload change. The SLM converts the request into a structured operation with a component, intent, and relevant constraints.

Step 2 — Candidate generation and ranking

Payload uses component information, reasoning, and candidate ranking to propose a suitable component. Deterministic checks validate applicable hard constraints.

Step 3 — Delivery feasibility

In the intended full workflow, Logistics determines whether the component can be delivered by the required deadline, while RAA supplies the relevant scheduling constraint.

Step 4 — Risk evaluation

Risk evaluates reported state and identifies whether a defined recovery action is needed. If the chosen component is infeasible because of its deadline, the intended P1 path signals Payload to reconsider it.

Step 5 — Commit the updated blueprint

Once a proposed modification has passed the necessary checks, the resulting configuration is persisted. Operation state should be recorded so an interrupted action can be recovered safely.

Step 6 — Report the outcome

The responsible agent returns a success/failure result to the SLM, which communicates the result to the user.

Steps 3 and 4 describe the intended multi-agent workflow. Because Logistics, RAA, and the running Risk Agent are not established as fully integrated in the current implementation, this should be presented as the designed end-to-end flow, not as a verified execution of the entire system.

## 12. Failure scenarios and recovery

The protocol is designed to handle several kinds of failure. These scenarios are particularly important because they explain why the agents need explicit communication contracts.

| Scenario                                       | Intended response                                 |
| ---------------------------------------------- | ------------------------------------------------- |
| Best component misses delivery deadline        | Risk issues P1; Payload reconsiders the candidate |
| Payload operation is interrupted               | P2 requests recovery from saved operation state   |
| Logistics cannot satisfy the required deadline | L1 signals the deadline conflict                  |
| Logistics fails to update state                | L2 requests recovery                              |
| An earlier delivery becomes feasible           | R1 signals that event ordering may need revision  |
| RAA is unresponsive or inconsistent            | R2 requests recovery                              |

A complete implementation should additionally address timeouts, duplicate messages, stale blueprint revisions, unavailable manufacturers, conflicting deadlines, and recovery attempts that fail repeatedly.

The important goal is not to eliminate every possible failure. It is to make failures detectable, assign responsibility for handling them, and avoid silently accepting an invalid configuration.

## 13. Implementation status

Based on the project information available in our conversation, the following is the safest summary.

| Component or feature                              | Status                                                               |
| ------------------------------------------------- | -------------------------------------------------------------------- |
| SLM orchestration using local quantized inference | Implemented vertical slice; routing primarily focuses on Payload     |
| Payload Agent                                     | Core implemented vertical slice                                      |
| Component data and preprocessing                  | Implemented                                                          |
| Gaussian Copula synthetic-data pipeline           | Implemented work is documented                                       |
| CatBoost candidate ranking                        | Part of the described technical implementation                       |
| Deterministic validation                          | Part of the described implementation                                 |
| SQLite/local state and blueprint management       | Part of the described implementation                                 |
| P1/P2 recovery-related code                       | Described as verified in code; full integration still needs evidence |
| Custom inter-agent protocol                       | Designed and specified                                               |
| Logistics Agent                                   | Protocol-level/planned                                               |
| RAA                                               | Protocol-level/planned                                               |
| Fully running Risk Agent                          | Not established as implemented                                       |
| Finance Agent                                     | Planned                                                              |
| Redis/Kafka integration                           | Not established as implemented                                       |
| Full multi-agent end-to-end workflow              | Not established as implemented                                       |

This distinction strengthens the technical credibility of the project report. It allows you to claim ownership of the broader architecture without suggesting that every subsystem is production-ready.

## 14. Testing and evaluation

The project notes report 46/46 tests passing, but those results have not been independently verified here. The report should identify them as README-reported results unless the actual test suite is run and its output recorded.

A more complete evaluation should cover:

- Functional correctness: adding, removing, and updating components.
- Constraint validity: ensuring proposed configurations satisfy hard constraints.
- Ranking quality: evaluating candidate ordering against a suitable baseline.
- Recovery correctness: injecting P1/P2 scenarios and checking the resulting state.
- State consistency: verifying that the blueprint and operation cache agree.
- Protocol correctness: testing malformed messages, invalid types, and missing fields.
- Performance: measuring inference latency, ranking latency, memory use, and end-to-end execution time.

For the most important demonstration, simulate a component that initially ranks first but later becomes infeasible because of its delivery deadline. Show the system selecting an alternative, validating it, and persisting the revised blueprint. Then inject a separate execution failure and demonstrate recovery without applying the same modification twice.

That would validate the two central behaviors of your design: replanning when a decision becomes invalid and recovering when execution is interrupted.

## 15. Final architectural summary

PAYLOAD-LOGIX is designed as a hybrid AI engineering system in which language models interpret requests, specialized agents handle domain-specific responsibilities, conventional software performs validation and ranking, and structured messages coordinate state changes and recovery.

Its main architectural contributions are:

1. A hub-and-spoke multi-agent design with distinct responsibilities.
2. A custom inter-agent communication specification for component operations, deadlines, status reporting, and recovery.
3. A hybrid reasoning pipeline combining local SLM inference, structured component data, CatBoost ranking, retrieval, and deterministic validation.
4. A blueprint and recovery model intended to preserve configuration state across operations.
5. Risk-triggered corrective behavior, particularly the distinction between invalidating an earlier decision and recovering from interrupted execution.

The most important principle tying these pieces together is that a component selection cannot be considered successful solely because it ranks highly. It must also satisfy the relevant engineering constraints, remain feasible within the integration schedule, and be reflected consistently in the system's state.

That is the central idea behind PAYLOAD-LOGIX: moving from isolated AI recommendations toward a coordinated engineering workflow that can respond to changing constraints and operational failures.
