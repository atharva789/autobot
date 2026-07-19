# Local Concept Tree

**Root status**: Approved for POC implementation
**Traversal rule**: Build the smallest falsification POC, compare it with the strongest substitute,
record evidence, then continue, refine, open-source, or kill. Adjacent children require a reviewed
design before implementation.

```text
Agentic Robot Design Evals                                      [building]
├── Agentic Robot Model-Repair Evals                           [candidate 1]
├── Causal Task-Conditioning Evals for Morphology Agents       [candidate 2]
├── Cheap-Proxy Calibration for Generated Robot Bodies         [candidate 3]
├── Controller-Budget Robustness Evals                         [candidate 4]
└── Active High-Fidelity Test Selection                        [candidate 5]

Next parent if this branch dies:
Agentic Physical-Systems Verification                          [unexplored]
```

## Root: Agentic Robot Design Evals

- **Buyer/job**: Robotics platform or simulation lead qualifying changes to a model, prompt, skill,
  MCP, plugin, or robot-description workflow.
- **POC**: Six isolated protected tasks, repeated agent trials, executable MuJoCo grades, replay, and
  comparison.
- **Strongest substitute**: One 300–500-line Python CLI plus Codex and task-specific tests.
- **Kill**: The control comes within one consequential catch, the delta is presentation/storage, or
  every task requires bespoke simulation engineering.
- **Possible defensible evidence**: Real failed repairs, protected behavior oracles, longitudinal
  profile regressions, and later physical-outcome calibration.

## Child 1: Agentic Robot Model-Repair Evals

- **Question**: Can executable preservation invariants separate agent configurations repairing
  IR/MJCF/URDF-derived assets?
- **POC**: Expand to 12 real-looking seeded faults and preserve exact semantic invariants.
- **Kill**: Static lint catches at least 90%, agents saturate the suite, or repairs are too infrequent.
- **Evidence**: Anonymized real model failures and failed agent repair traces.

## Child 2: Causal Task-Conditioning Evals

- **Question**: Does correct task language cause useful morphology changes?
- **POC**: Correct, shuffled, generic, and grammar-only conditions on matched task pairs.
- **Kill**: Correct conditioning does not beat shuffled/generic controls or changes only names/prose.
- **Evidence**: Hidden counterfactual tasks and causal task-sensitivity results.

## Child 3: Cheap-Proxy Calibration

- **Question**: Which compile/static/zero-control screens predict an executed downstream outcome?
- **POC**: Pair 30–50 bodies and cheap screens with an equal-budget local control oracle.
- **Kill**: Held-out correlations vanish, reverse under perturbation, or labels cost as much as full
  evaluation.
- **Evidence**: Calibration curves, false-reject regions, and explicit claim boundaries.

## Child 4: Controller-Budget Robustness

- **Question**: Does the selected body remain selected across fair controller-search budgets?
- **POC**: Twelve morphologies at four identical controller budgets.
- **Kill**: Rankings are trivially stable, bodies lack comparable control interfaces, or local compute
  cannot produce replicated curves.
- **Evidence**: Per-body learning curves and ranking-sensitivity measurements.

## Child 5: Active High-Fidelity Test Selection

- **Question**: Can cheap evidence choose the next expensive simulator, HIL, or physical test?
- **POC**: Compare random, uncertainty, and simple multifidelity selection against a more expensive
  local oracle.
- **Kill**: Simple uncertainty matches the method, expensive tests are cheap, or fidelity levels have
  no predictive relationship.
- **Evidence**: Fewer expensive tests at fixed decision accuracy and eventually paired physical data.

## Next parent: Agentic Physical-Systems Verification

- **Buyer/job**: Prevent agent-generated CAD, robot description, controller, ROS, calibration, or test
  changes from reaching expensive simulation or hardware with silent physical errors.
- **POC**: One reference robot with 20 cross-artifact seeded faults and executable invariants.
- **Strongest substitute**: Existing engineering CI plus an agent writing missing tests.
- **Kill**: Problems reduce to ordinary lint/unit tests, do not generalize beyond one stack, or teams
  will not share incident artifacts.
- **Evidence**: A private taxonomy of cross-artifact physical failures and escaped defects.
