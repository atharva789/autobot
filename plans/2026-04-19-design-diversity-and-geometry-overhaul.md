# Design Diversity and Geometry Overhaul Plan

**Date**: 2026-04-19
**Priority**: Critical
**Estimated effort**: 12-16 hours

## Problem Statement

Three critical issues are blocking the app from being demo-ready:

1. **Repetitive robot designs**: The generator produces the same 3 design archetypes repeatedly (biped, quadruped, arm-only) regardless of task diversity
2. **Undersized morphology canvas**: The 3D viewer is constrained to a small panel, limiting the "wow factor"
3. **Photon HITL not delivering**: iMessage notifications are not being sent despite the transport layer existing

## Root Cause Analysis

### Issue 1: Repetitive Designs

**Current state**:
- `design_generator.py` uses Gemini 2.5 Pro with a compact schema
- Few-shot example heavily biases toward proven topologies (biped/quadruped)
- Diversity override threshold is too gentle (0.02 margin)
- History context (`prior_design_contexts`) rarely passed
- Prompt variants are subtle, not fundamentally different

**Why the same 3 designs appear**:
1. Few-shot example shows exactly 3 designs: biped, quadruped, and simplified biped
2. The model learns "safe" patterns and repeats them
3. Diversity penalties are weak (0.42 threshold for history similarity)
4. No contrastive generation signals forcing truly different embodiments

### Issue 2: Small Canvas

**Current state**:
- MorphologyViewer is embedded in a `min-h-[760px]` panel
- No full-screen or expandable view mode
- Canvas constrained by fixed grid layout

### Issue 3: Photon Not Working

**Current state**:
- Transport layer exists (`photon.py`)
- `SpectrumCliPhotonTransport` calls `photon_send.mjs`
- BUT: Environment variables likely not set (`PHOTON_PROJECT_ID`, `PHOTON_SECRET_KEY`)
- AND: No verification that the Spectrum CLI script actually works

---

## Improvement Plan

### Phase A: Design Diversity Overhaul (8-10 hours)

#### A1: Implement Contrastive Generation (3 hours)

Replace the current "generate 3 candidates" approach with **forced divergence**:

```python
# New prompt structure
CANDIDATE_PROMPTS = {
    "A": "Design a CONVENTIONAL solution using the most proven topology for this task. Prefer established embodiment patterns with minimal novelty.",
    "B": "Design an UNCONVENTIONAL solution that challenges assumptions. Use a different embodiment class than typical. Explore hybrid topologies, non-anthropomorphic layouts, or task-specialized morphologies.",
    "C": "Design a MINIMAL solution prioritizing simplicity and buildability. Fewest actuated joints possible. Could be a single manipulator, wheeled base, or underactuated design."
}
```

**Implementation**:
1. Generate each candidate with a separate Gemini call
2. Pass previous candidates as "already proposed" context to force divergence
3. Add explicit constraints: "Your design MUST differ from: {prior_embodiments}"

#### A2: Richer Embodiment Vocabulary (2 hours)

Expand the `embodiment_class` enum beyond the current 6 options:

```python
EMBODIMENT_CLASSES = [
    # Legged
    "biped", "quadruped", "hexapod", "tripod",
    # Wheeled/tracked
    "wheeled", "tracked", "omnidirectional",
    # Hybrid
    "wheeled_manipulator", "legged_wheeled", "climbing_hybrid",
    # Specialized
    "snake", "inchworm", "spherical", "tensegrity",
    # Manipulation-only
    "fixed_arm", "mobile_arm", "dual_arm",
    # Novel
    "modular", "swarm_unit", "soft_continuum"
]
```

#### A3: Task-Conditioned Morphology Priors (2 hours)

Create a task-to-embodiment recommendation system that suggests appropriate topologies:

```python
TASK_EMBODIMENT_PRIORS = {
    "climbing": ["climbing_hybrid", "hexapod", "quadruped", "snake"],
    "stairs": ["biped", "quadruped", "tracked"],
    "manipulation": ["dual_arm", "mobile_arm", "wheeled_manipulator"],
    "payload_transport": ["quadruped", "wheeled", "tracked"],
    "rough_terrain": ["hexapod", "tracked", "legged_wheeled"],
    "confined_space": ["snake", "inchworm", "soft_continuum"],
}
```

Instead of injecting "do not" rules, inject **positive affordance requirements**:
- "This task requires vertical surface adhesion capability"
- "This task requires maintaining 3-point contact during locomotion"
- "This task benefits from a low center of mass and wide stance"

#### A4: Strengthen Diversity Enforcement (1 hour)

Update `design_diversity.py`:

```python
# Increase thresholds
BATCH_SIMILARITY_THRESHOLD = 0.55  # Was 0.78
HISTORY_SIMILARITY_THRESHOLD = 0.30  # Was 0.42
OVERRIDE_SCORE_MARGIN = 0.08  # Was 0.02

# Add hard rejection for identical embodiment classes in same batch
def validate_batch_diversity(candidates: list[RobotDesignCandidate]) -> bool:
    embodiments = [c.embodiment_class for c in candidates]
    if len(set(embodiments)) < len(candidates):
        return False  # Reject if any embodiment repeated
    return True
```

#### A5: Diverse Few-Shot Exemplar Bank (1 hour)

Create a bank of 12+ diverse examples, randomly sample 3 per generation:

```
exemplars/
├── climbing_hexapod.json
├── warehouse_wheeled_arm.json
├── rescue_snake.json
├── inspection_quadrotor.json
├── payload_tracked.json
├── assembly_dual_arm.json
├── slope_tensegrity.json
├── pipe_inchworm.json
├── stair_biped.json
├── underwater_hybrid.json
├── modular_reconfigurable.json
└── soft_continuum.json
```

---

### Phase B: Geometry and Canvas Improvements (3-4 hours)

#### B1: Full-Screen Morphology View (1.5 hours)

Add an expandable/full-screen mode for the 3D canvas:

```tsx
// New component: FullscreenMorphologyModal.tsx
function FullscreenMorphologyModal({ candidate, onClose }) {
  return (
    <Dialog open onOpenChange={onClose} className="max-w-[95vw] max-h-[95vh]">
      <div className="h-[90vh] w-[90vw]">
        <MorphologyViewer 
          candidate={candidate} 
          mode="engineering"
          animated={true}
        />
      </div>
    </Dialog>
  );
}
```

Add expand button to the current canvas that opens this modal.

#### B2: Scrollable Robot Detail View (1 hour)

Modify the detail panel to allow vertical scrolling with the robot visible:

```tsx
// In page.tsx, update the detail view section
<section className="relative flex h-[calc(100vh-120px)] flex-col overflow-y-auto">
  <div className="sticky top-0 z-10 h-[50vh] min-h-[400px]">
    <MorphologyViewer ... />
  </div>
  <div className="flex-1 p-6">
    {/* Spec/Component/Export tabs content here */}
  </div>
</section>
```

#### B3: Component Geometry Library Expansion (1.5 hours)

Add richer primitive/accessory geometry to `engineering_render.py`:

```python
EXTENDED_MESH_LIBRARY = {
    # Structural
    "torso_shell": {...},
    "torso_box": {"primitive": "box", "material": "composite_shell"},
    "torso_cylinder": {"primitive": "cylinder", "material": "anodized_metal"},
    
    # Locomotion
    "wheel_hub": {"primitive": "cylinder", "material": "rubber_tire"},
    "track_segment": {"primitive": "box", "material": "rubber_track"},
    "flipper_arm": {"primitive": "box", "material": "anodized_metal"},
    
    # Climbing
    "microspine_array": {"primitive": "cone_array", "material": "steel"},
    "suction_cup": {"primitive": "hemisphere", "material": "silicone"},
    "magnetic_pad": {"primitive": "cylinder", "material": "neodymium"},
    
    # End effectors
    "parallel_gripper": {"primitive": "gripper_mesh", "material": "anodized_metal"},
    "vacuum_gripper": {"primitive": "cylinder", "material": "silicone"},
    "soft_finger": {"primitive": "tapered_cylinder", "material": "silicone"},
}
```

---

### Phase C: Photon HITL Integration Fix (2 hours)

#### C1: Environment Variable Verification (30 min)

Add startup check and clear error messages:

```python
# In demo/app.py startup
def verify_photon_config():
    if not photon_provider_ready():
        logger.warning(
            "Photon HITL not configured. Set PHOTON_PROJECT_ID and "
            "PHOTON_SECRET_KEY for iMessage notifications."
        )
        return False
    
    # Test connectivity
    try:
        messenger = build_photon_messenger_from_env()
        # Send test ping
        result = messenger.send_text(
            recipient=os.environ.get("PHOTON_TEST_RECIPIENT", ""),
            text="[AutoBot] Connection test",
        )
        if not result.ok:
            logger.error(f"Photon test failed: {result.raw_response}")
            return False
    except Exception as e:
        logger.error(f"Photon initialization failed: {e}")
        return False
    
    return True
```

#### C2: Spectrum CLI Script Verification (1 hour)

Update `apps/web/scripts/photon_send.mjs`:

```javascript
import { Spectrum } from 'spectrum-ts';

const config = {
  projectId: process.env.PHOTON_PROJECT_ID,
  secretKey: process.env.PHOTON_SECRET_KEY,
};

async function main() {
  const input = JSON.parse(await readStdin());
  
  const spectrum = new Spectrum(config);
  
  // Ensure user exists in Spectrum
  const user = await spectrum.users.getOrCreate({
    externalId: input.recipient,
    phone: input.recipient,
  });
  
  // Send based on kind
  if (input.kind === 'poll') {
    const result = await spectrum.messages.sendPoll({
      userId: user.id,
      question: input.question,
      options: input.options.map(o => ({ label: o.label, value: o.value })),
    });
    console.log(JSON.stringify({ ok: true, id: result.id }));
  } else {
    const result = await spectrum.messages.sendText({
      userId: user.id,
      text: input.text,
    });
    console.log(JSON.stringify({ ok: true, id: result.id }));
  }
}

main().catch(e => {
  console.error(JSON.stringify({ ok: false, error: e.message }));
  process.exit(1);
});
```

#### C3: UI Feedback for HITL State (30 min)

Show Photon status in the workspace:

```tsx
// Add to workspace header
function PhotonStatusBadge() {
  const { hitlSetup } = useDesignRuntime();
  
  if (!hitlSetup?.provider_configured) {
    return (
      <Badge variant="outline" className="text-amber-500 border-amber-500/50">
        HITL not configured
      </Badge>
    );
  }
  
  return (
    <Badge variant="outline" className="text-emerald-500 border-emerald-500/50">
      HITL active
    </Badge>
  );
}
```

---

## Implementation Order

1. **Phase A1-A2** (Contrastive generation + embodiment vocabulary) - Immediate impact
2. **Phase B1** (Full-screen view) - Quick win for demos
3. **Phase C1-C2** (Photon fix) - Unblock HITL testing
4. **Phase A3-A5** (Task priors + diversity + exemplars) - Deeper improvement
5. **Phase B2-B3** (Scrollable view + geometry library) - Polish

## Success Criteria

1. **Diversity**: Running the same prompt 5 times yields at least 3 distinct embodiment classes across all candidates
2. **Canvas**: User can view robot at full viewport height, rotate/zoom smoothly
3. **Photon**: Send a test poll to a verified phone number and receive it

## Files to Modify

**Design diversity**:
- `packages/pipeline/design_generator.py`
- `packages/pipeline/design_prompts.py`
- `packages/pipeline/design_diversity.py`
- `packages/pipeline/schemas.py`
- New: `packages/pipeline/exemplars/*.json`

**Canvas**:
- `apps/web/app/page.tsx`
- `apps/web/components/MorphologyViewer.tsx`
- New: `apps/web/components/FullscreenMorphologyModal.tsx`

**Geometry**:
- `packages/pipeline/engineering_render.py`

**Photon**:
- `packages/pipeline/photon.py`
- `apps/web/scripts/photon_send.mjs`
- `demo/app.py`
- `.env.example`

## Research References

- **RoboMorph**: Evolving robot morphology using LLMs with grammar-based representations
- **G2 (Guided Generation)**: Contrastive signals for diversity without quality loss
- **Verbalized Sampling**: Request explicit probability distributions for 1.6-2.1x diversity
- **AIDL**: Solver-aided DSL offloading spatial reasoning to constraint solvers
- **CAD-LLM / STEP-LLM**: Structured CAD generation from natural language
