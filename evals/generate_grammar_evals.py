"""Generate 700+ eval entries for the RoboGrammar structural rule agent loop.

Run:  python -m evals.generate_grammar_evals

Writes evals/grammar_evals.json validated against the vocab snapshot.
"""

from __future__ import annotations

import json
import random
import string
from collections.abc import Iterator

SNAPSHOT = "evals/grammar_vocab_snapshot.json"
OUTPUT = "evals/grammar_evals.json"

random.seed(42)


def _load_vocab() -> tuple[set[str], set[str], list[dict], list[dict]]:
    with open(SNAPSHOT) as f:
        data = json.load(f)
    nt = {n["short_form_name"] for n in data["nodes"] if n["node_type"] == "nonterminal"}
    t = {n["short_form_name"] for n in data["nodes"] if n["node_type"] == "terminal"}
    return nt, t, data["nodes"], data["rules"]


NT, T, NODES, RULES = _load_vocab()
ALL = NT | T


ORPHAN_NT = {
    "CLIMBING_LEG", "CLIMBING_LEG_PAIR", "DIGITIGRADE_LEG_PAIR",
    "END_EFFECTOR", "FOLDED_WING_PAIR", "FOOT", "HEEL", "LOAD_BAY",
    "SHORT_LEG", "SHORT_LEG_PAIR", "SPINE", "SPRAWLED_LEG",
    "SPRING_LEG_PAIR", "TALON", "TARSUS", "TOE",
}


ROBOT_FAMILIES = {
    "humanoid": {
        "S": ["TORSO", "PELVIS", "HEAD", "ARM_PAIR", "LEG_PAIR"],
        "ARM_PAIR": ["ARM", "ARM"],
        "LEG_PAIR": ["LEG", "LEG"],
        "ARM": ["shoulder_joint", "arm_link", "elbow_joint", "limb_link", "wrist_joint", "hand"],
        "LEG": ["hip_joint", "upper_leg", "knee_joint", "lower_leg", "foot_pad"],
    },
    "quadruped": {
        "S": ["BODY"],
        "BODY": ["BODY_CHAIN", "LEG_PAIR", "LEG_PAIR", "TAIL"],
        "BODY_CHAIN": ["BODY_SEG", "BODY_SEG"],
        "LEG": ["HIP_STACK", "thigh_link", "knee_joint", "shank_link", "foot_pad"],
        "HIP_STACK": ["hip_yaw", "hip_roll", "hip_pitch"],
    },
    "biped": {
        "S": ["BODY"],
        "BODY": ["TORSO", "LEG_PAIR", "ARM_PAIR"],
        "LEG": ["hip_joint", "upper_leg", "knee_joint", "lower_leg", "foot_pad"],
        "DIGITIGRADE_LEG": ["hip_pitch", "thigh_link", "reverse_knee", "heel_link", "toe_pad"],
    },
    "hexapod": {
        "S": ["BODY"],
        "BODY": ["THORAX_CHAIN"],
        "THORAX_CHAIN": ["THORAX_SEG", "THORAX_SEG", "THORAX_SEG"],
        "THORAX_SEG": ["LEG_PAIR"],
        "LEG": ["hip_joint", "femur_link", "knee_joint", "tibia_link", "foot_pad"],
    },
    "snake": {
        "S": ["BODY"],
        "BODY": ["BODY_CHAIN", "HEAD"],
        "BODY_CHAIN": ["vertebra_link", "yaw_joint", "BODY_CHAIN"],
        "HEAD": ["camera_head"],
    },
    "centipede": {
        "S": ["BODY"],
        "BODY": ["SEG_CHAIN"],
        "SEG_CHAIN": ["SEG", "flex_joint", "SEG_CHAIN"],
        "SEG": ["body_segment", "LEG_PAIR"],
    },
    "bird": {
        "S": ["BODY", "WING_PAIR", "LEG_PAIR", "NECK", "HEAD"],
        "WING_PAIR": ["WING", "WING"],
        "WING": ["shoulder_joint", "wing_link", "feather_panel"],
        "PERCHING_LEG": ["hip_joint", "shin_link", "ankle_joint", "opposable_talon"],
    },
    "lizard": {
        "S": ["BODY"],
        "BODY": ["TRUNK", "SPRAWLED_LEG_PAIR", "SPRAWLED_LEG_PAIR", "TAIL"],
        "TRUNK": ["flat_trunk", "reinforced_torso"],
        "TAIL": ["tail_yaw", "tail_link", "tail_tip"],
        "ADHESIVE_FOOT": ["toe_splay_joint", "adhesive_pad"],
    },
    "arachnid": {
        "S": ["BODY"],
        "BODY": ["LEG_PAIR", "LEG_PAIR", "LEG_PAIR", "LEG_PAIR"],
        "LEG": ["hip_joint", "femur_link", "tibia_joint", "tarsus_tip"],
    },
    "wheeled": {
        "S": ["BODY"],
        "BODY": ["BODY_CHAIN", "TERMINAL_CONTACT", "TERMINAL_CONTACT"],
        "BODY_CHAIN": ["body_link", "body_connector", "body_link"],
        "TERMINAL_CONTACT": ["wheel"],
    },
    "hybrid_walker": {
        "S": ["BODY"],
        "BODY": ["TORSO", "LEG_PAIR", "LEG_PAIR", "ARM_PAIR"],
        "LEG": ["hip_joint", "thigh_link", "knee_joint", "shank_link", "foot_pad"],
        "ARM": ["shoulder_joint", "limb_link", "elbow_joint", "hand"],
    },
}

TASK_PROMPTS = {
    "humanoid": [
        "Design a humanoid robot that can walk on rough terrain",
        "Build a bipedal humanoid for warehouse box handling",
        "Create a humanoid assistant robot for elderly care",
        "Design a humanoid robot for search and rescue in rubble",
        "Build a humanoid robot that can climb ladders",
        "Create a humanoid robot for manufacturing assembly lines",
        "Design a humanoid robot for underwater exploration",
        "Build a humanoid firefighting robot",
        "Create a humanoid robot barista that can serve drinks",
        "Design a humanoid robot for surgical assistance",
    ],
    "quadruped": [
        "Design a four-legged robot for mountain trail patrol",
        "Build a quadruped robot for agricultural field inspection",
        "Create a dog-like robot for home security patrol",
        "Design a quadruped pack mule for military supply transport",
        "Build a four-legged robot for pipeline inspection in tunnels",
        "Create a quadruped robot for snow terrain navigation",
        "Design a four-legged robot for forest fire monitoring",
        "Build a quadruped robot for underground mine exploration",
        "Create a horse-like robot for rough terrain delivery",
        "Design a quadruped robot for disaster area mapping",
    ],
    "biped": [
        "Design a lightweight bipedal robot for indoor navigation",
        "Build a biped robot with digitigrade legs for fast running",
        "Create a bipedal robot for stair climbing in office buildings",
        "Design a two-legged robot for flat warehouse floors",
        "Build a bipedal robot with spring legs for jumping obstacles",
        "Create a biped robot for sidewalk delivery",
        "Design a bipedal robot for construction site monitoring",
        "Build a two-legged robot for library book retrieval",
        "Create a biped runner robot for athletic competitions",
        "Design a bipedal robot for elevator-accessible buildings",
    ],
    "hexapod": [
        "Design a six-legged robot for rough terrain exploration",
        "Build a hexapod for crawling through disaster rubble",
        "Create an insect-like robot for agricultural pest monitoring",
        "Design a hexapod robot for planetary surface exploration",
        "Build a six-legged robot for nuclear facility inspection",
        "Create a hexapod for underwater coral reef monitoring",
        "Design a six-legged robot for bridge underside inspection",
        "Build a hexapod robot for mine clearance operations",
        "Create an insect-scale hexapod for ventilation duct inspection",
        "Design a hexapod robot for vertical wall climbing",
    ],
    "snake": [
        "Design a snake robot for pipe inspection",
        "Build a serpentine robot for earthquake rubble penetration",
        "Create a snake-like robot for cable conduit navigation",
        "Design a snake robot for archaeological excavation access",
        "Build a serpentine robot for surgical endoscopy",
        "Create a snake robot for sewer inspection",
        "Design a snake-like robot for nuclear reactor inspection",
        "Build a serpentine robot for tree canopy exploration",
        "Create a snake robot for deep borehole inspection",
        "Design a snake-like robot for submarine hull inspection",
    ],
    "centipede": [
        "Design a centipede robot for tunnel exploration",
        "Build a many-legged robot for rough terrain adaptability",
        "Create a centipede-like robot for pipe crawling",
        "Design a segmented robot for confined space navigation",
        "Build a centipede robot for agricultural soil monitoring",
        "Create a multi-segment robot for underwater pipeline inspection",
        "Design a centipede robot for vertical shaft descent",
        "Build a segmented robot for rubble crawling after earthquakes",
        "Create a centipede-like robot for mine shaft navigation",
        "Design a many-legged robot for forest floor exploration",
    ],
    "bird": [
        "Design a bird-like robot for aerial surveillance with perching",
        "Build an avian robot for power line inspection with landing",
        "Create a bird robot for wildlife monitoring in forests",
        "Design a perching drone for bridge inspection",
        "Build a bird-like robot for pest control in orchards",
        "Create an avian robot for weather station maintenance",
        "Design a bird robot for search and rescue with perching ability",
        "Build a bird-like robot for wind turbine blade inspection",
        "Create an avian robot for cliff-face geological sampling",
        "Design a bird robot for urban rooftop monitoring",
    ],
    "lizard": [
        "Design a gecko-inspired robot for wall climbing inspection",
        "Build a lizard-like robot for solar panel cleaning on facades",
        "Create a gecko robot for window cleaning on skyscrapers",
        "Design a lizard robot for vertical surface navigation",
        "Build a gecko-inspired robot for aircraft fuselage inspection",
        "Create a lizard-like robot for rock face geological survey",
        "Design a gecko robot for indoor ceiling inspection",
        "Build a lizard-like robot for ship hull maintenance",
        "Create a gecko-inspired robot for tunnel wall monitoring",
        "Design a lizard robot for chimney inspection",
    ],
    "arachnid": [
        "Design an eight-legged robot for web-like structure building",
        "Build a spider-like robot for tight space exploration",
        "Create an arachnid robot for ceiling navigation",
        "Design a spider robot for 3D printing in construction",
        "Build an eight-legged robot for irregular terrain mapping",
        "Create an arachnid robot for cable installation in ceilings",
        "Design a spider-like robot for greenhouse pest monitoring",
        "Build an eight-legged robot for archaeological site surveying",
        "Create an arachnid robot for warehouse inventory scanning",
        "Design a spider robot for structural inspection under bridges",
    ],
    "wheeled": [
        "Design a wheeled robot for flat warehouse floor navigation",
        "Build a wheeled robot for hospital corridor delivery",
        "Create a wheeled platform for office mail delivery",
        "Design a wheeled robot for airport terminal patrolling",
        "Build a wheeled robot for supermarket shelf scanning",
        "Create a wheeled robot for museum tour guidance",
        "Design a wheeled robot for parking lot monitoring",
        "Build a wheeled platform for library book transport",
        "Create a wheeled robot for data center aisle patrol",
        "Design a wheeled robot for greenhouse watering",
    ],
    "hybrid_walker": [
        "Design a robot with four legs and two arms for manipulation while walking",
        "Build a centaur-like robot for field archaeology",
        "Create a hybrid walker that can carry and place objects",
        "Design a four-legged robot with manipulator arms for construction",
        "Build a centaur robot for forestry management tasks",
        "Create a hybrid walker for underwater sample collection",
        "Design a four-legged robot with arms for warehouse logistics",
        "Build a centaur-like robot for agricultural harvesting",
        "Create a hybrid walker for hazardous material handling",
        "Design a four-legged robot with arms for elderly assistance",
    ],
}


def _misspell(name: str) -> str:
    if len(name) < 3:
        return name + random.choice(string.ascii_lowercase)
    op = random.choice(["swap", "drop", "add", "sub"])
    i = random.randint(1, len(name) - 2)
    if op == "swap" and i < len(name) - 1:
        return name[:i] + name[i + 1] + name[i] + name[i + 2:]
    elif op == "drop":
        return name[:i] + name[i + 1:]
    elif op == "add":
        return name[:i] + random.choice(string.ascii_lowercase) + name[i:]
    else:
        return name[:i] + random.choice(string.ascii_lowercase) + name[i + 1:]


INVENTED_NODES = [
    "servo_actuator", "pneumatic_piston", "gyro_stabilizer", "force_sensor",
    "lidar_turret", "battery_pack", "thermal_radiator", "shock_absorber",
    "hydraulic_cylinder", "carbon_frame", "titanium_strut", "nano_gripper",
    "solar_panel", "antenna_mast", "cooling_fan", "pressure_valve",
    "motor_housing", "bearing_mount", "cable_guide", "heat_sink",
    "rubber_tread", "magnetic_foot", "suction_cup", "spring_damper",
    "torque_limiter", "encoder_disk", "potentiometer", "load_cell",
    "infrared_sensor", "ultrasonic_emitter", "gps_module", "imu_board",
    "vision_module", "depth_camera", "microphone_array", "speaker_unit",
    "led_strip", "laser_pointer", "fiber_optic", "power_rail",
]

INVENTED_NT = [
    "PROPELLER", "ROTOR_PAIR", "TURRET", "CHASSIS",
    "DRIVETRAIN", "SUSPENSION", "BUMPER", "STABILIZER_FIN",
    "CLAW", "PINCER_PAIR", "TENTACLE", "FLIPPER",
    "TRACK_ASSEMBLY", "HOVER_PAD", "JET_NOZZLE", "BLADE_PAIR",
    "ANTENNA_BOOM", "SOLAR_ARRAY", "CARGO_BAY", "DOCKING_PORT",
]

ANATOMY_NODES = [
    "femur", "tibia", "fibula", "patella", "metatarsal",
    "phalanx", "scapula", "humerus", "radius", "ulna",
    "pelvis_bone", "sacrum", "coccyx", "sternum", "clavicle",
    "vertebra", "rib", "cranium", "mandible", "maxilla",
    "deltoid", "bicep", "tricep", "quadricep", "hamstring",
    "gastrocnemius", "achilles", "rotator_cuff", "trapezius", "latissimus",
    "metacarpal", "carpal", "tarsal", "calcaneus", "talus",
    "meniscus", "ligament", "tendon", "cartilage", "synovial_joint",
]


def gen_valid_baseline() -> Iterator[dict]:
    idx = 0
    for family, template in ROBOT_FAMILIES.items():
        prompts = TASK_PROMPTS.get(family, [])
        for prompt in prompts:
            idx += 1
            rules = dict(template)
            if idx % 3 == 0 and "BODY_CHAIN" in rules:
                rules = {k: v for k, v in rules.items() if k != "BODY_CHAIN"}
                rules["BODY_CHAIN"] = ["BODY_SEG"]

            yield {
                "id": f"valid_{idx:03d}",
                "prompt": prompt,
                "expected_rules": rules,
                "tag": "valid_baseline",
                "subtag": family,
                "expected_compile_safe": True,
                "expected_invalid_nodes": [],
                "expected_behavior": "produce",
                "difficulty": "easy" if family in ("humanoid", "quadruped", "wheeled") else "medium",
                "notes": f"Standard {family} morphology for: {prompt[:60]}",
                "source_family": family,
            }


def gen_hallucination_misspell() -> Iterator[dict]:
    idx = 0
    for family, template in ROBOT_FAMILIES.items():
        for _ in range(10):
            idx += 1
            rules = dict(template)
            key = random.choice(list(rules.keys()))
            rhs = list(rules[key])
            original = ""
            corrupted = ""
            if rhs:
                target_idx = random.randint(0, len(rhs) - 1)
                original = rhs[target_idx]
                corrupted = _misspell(original)
                while corrupted in ALL or corrupted == original:
                    corrupted = _misspell(original)
                rhs[target_idx] = corrupted
                rules[key] = rhs
                invalid = [corrupted]
            else:
                original = key
                corrupted = _misspell(key)
                while corrupted in ALL:
                    corrupted = _misspell(key)
                rules[corrupted] = rules.pop(key)
                invalid = [corrupted]

            prompt_pool = TASK_PROMPTS.get(family, ["Design a robot"])
            yield {
                "id": f"hall_misspell_{idx:03d}",
                "prompt": random.choice(prompt_pool),
                "expected_rules": rules,
                "tag": "hallucination_misspell",
                "subtag": f"typo_in_{key}",
                "expected_compile_safe": False,
                "expected_invalid_nodes": invalid,
                "expected_behavior": "reject",
                "difficulty": "easy",
                "notes": f"Misspelled '{original}' as '{corrupted}' in {family} {key} rule",
                "source_family": family,
            }


def gen_hallucination_invent() -> Iterator[dict]:
    idx = 0
    for family, template in ROBOT_FAMILIES.items():
        for _ in range(7):
            idx += 1
            rules = dict(template)
            key = random.choice(list(rules.keys()))
            rhs = list(rules[key])
            invented = random.choice(INVENTED_NODES)
            if rhs:
                rhs[random.randint(0, len(rhs) - 1)] = invented
            else:
                rhs = [invented]
            rules[key] = rhs

            prompt_pool = TASK_PROMPTS.get(family, ["Design a robot"])
            yield {
                "id": f"hall_invent_{idx:03d}",
                "prompt": random.choice(prompt_pool),
                "expected_rules": rules,
                "tag": "hallucination_invent",
                "subtag": "invented_terminal",
                "expected_compile_safe": False,
                "expected_invalid_nodes": [invented],
                "expected_behavior": "reject",
                "difficulty": "easy",
                "notes": f"Invented node '{invented}' injected into {family} {key}",
                "source_family": family,
            }

    for _ in range(5):
        idx += 1
        inv_nt = random.choice(INVENTED_NT)
        rules = {"S": ["BODY"], "BODY": [inv_nt, "LEG_PAIR"], inv_nt: ["body_link"]}
        yield {
            "id": f"hall_invent_{idx:03d}",
            "prompt": "Design a robot with custom morphology",
            "expected_rules": rules,
            "tag": "hallucination_invent",
            "subtag": "invented_nonterminal",
            "expected_compile_safe": False,
            "expected_invalid_nodes": [inv_nt],
            "expected_behavior": "reject",
            "difficulty": "medium",
            "notes": f"Invented nonterminal '{inv_nt}' used as intermediate symbol",
            "source_family": "",
        }


def gen_hallucination_orphan() -> Iterator[dict]:
    idx = 0
    orphan_list = sorted(ORPHAN_NT)
    for orphan in orphan_list:
        idx += 1
        rules = {
            "S": ["BODY"],
            "BODY": ["BODY_CHAIN", orphan],
            orphan: ["body_link", "foot_pad"],
        }
        yield {
            "id": f"hall_orphan_{idx:03d}",
            "prompt": f"Design a robot using a {orphan.lower().replace('_', ' ')} component",
            "expected_rules": rules,
            "tag": "hallucination_orphan",
            "subtag": orphan,
            "expected_compile_safe": True,
            "expected_invalid_nodes": [],
            "expected_behavior": "flag_infeasible",
            "difficulty": "hard",
            "notes": f"Orphan NT '{orphan}' compiles (in vocab) but has no canonical expansion rules",
            "source_family": "",
        }

    for _ in range(14):
        idx += 1
        orphan = random.choice(orphan_list)
        family = random.choice(list(ROBOT_FAMILIES.keys()))
        rules = dict(ROBOT_FAMILIES[family])
        inject_key = random.choice(list(rules.keys()))
        rhs = list(rules[inject_key])
        rhs.append(orphan)
        rules[inject_key] = rhs
        rules[orphan] = ["body_link"]

        yield {
            "id": f"hall_orphan_{idx:03d}",
            "prompt": random.choice(TASK_PROMPTS.get(family, ["Design a robot"])),
            "expected_rules": rules,
            "tag": "hallucination_orphan",
            "subtag": f"{orphan}_in_{family}",
            "expected_compile_safe": True,
            "expected_invalid_nodes": [],
            "expected_behavior": "flag_infeasible",
            "difficulty": "hard",
            "notes": f"Orphan '{orphan}' injected into {family} rules — compiles but semantically wrong",
            "source_family": family,
        }


def gen_recursion_no_base() -> Iterator[dict]:
    idx = 0
    recursive_patterns = [
        ("BODY_CHAIN", ["BODY_SEG", "BODY_CHAIN"], "body chain without terminator"),
        ("SEG_CHAIN", ["SEG", "flex_joint", "SEG_CHAIN"], "segment chain without terminator"),
        ("SPINE_CHAIN", ["BODY_SEG", "spine_yaw", "SPINE_CHAIN"], "spine chain without terminator"),
        ("THORAX_CHAIN", ["THORAX_SEG", "THORAX_CHAIN"], "thorax chain without terminator"),
    ]
    prompts = [
        "Design a long segmented robot",
        "Build a centipede-like robot with many segments",
        "Create a snake robot with repeating vertebrae",
        "Design a long-bodied quadruped robot",
        "Build a modular robot with chainable segments",
        "Create a robot with an extensible spine",
        "Design a robot with repeating thorax segments",
        "Build a robot with unlimited body extension",
    ]

    for lhs, rhs, desc in recursive_patterns:
        for p in prompts[:5]:
            idx += 1
            rules = {"S": ["BODY"], "BODY": [lhs], lhs: rhs}
            yield {
                "id": f"rec_nobase_{idx:03d}",
                "prompt": p,
                "expected_rules": rules,
                "tag": "recursion_no_base",
                "subtag": lhs,
                "expected_compile_safe": True,
                "expected_invalid_nodes": [],
                "expected_behavior": "reject",
                "difficulty": "hard",
                "notes": f"Recursive {desc} — no base case to terminate expansion",
                "source_family": "",
            }


def gen_recursion_self_only() -> Iterator[dict]:
    idx = 0
    self_ref_nts = ["BODY_CHAIN", "SEG_CHAIN", "BODY", "LEG", "ARM", "SPINE_CHAIN"]
    prompts = [
        "Design a robot that can extend itself",
        "Build a self-replicating robot morphology",
        "Create a robot with fractal body structure",
        "Design a recursive robot design",
    ]

    for nt in self_ref_nts:
        for p in prompts:
            idx += 1
            rules = {"S": [nt], nt: [nt]}
            yield {
                "id": f"rec_self_{idx:03d}",
                "prompt": p,
                "expected_rules": rules,
                "tag": "recursion_self_only",
                "subtag": nt,
                "expected_compile_safe": True,
                "expected_invalid_nodes": [],
                "expected_behavior": "reject",
                "difficulty": "medium",
                "notes": f"Pure self-reference: {nt} -> {nt} creates infinite loop",
                "source_family": "",
            }


def gen_recursion_overuse() -> Iterator[dict]:
    idx = 0
    overuse_cases = [
        {
            "rules": {
                "S": ["BODY"],
                "BODY": ["BODY_CHAIN", "LEG_PAIR", "LEG_PAIR"],
                "BODY_CHAIN": ["BODY_SEG", "BODY_CHAIN"],
                "LEG_PAIR": ["LEG", "LEG"],
                "LEG": ["hip_joint", "LEG"],
            },
            "desc": "LEG recurses into itself while also in BODY_CHAIN recursion",
        },
        {
            "rules": {
                "S": ["SEG_CHAIN"],
                "SEG_CHAIN": ["SEG", "SEG_CHAIN"],
                "SEG": ["BODY_CHAIN", "LEG_PAIR"],
                "BODY_CHAIN": ["BODY_SEG", "SEG_CHAIN"],
            },
            "desc": "Mutual recursion between SEG_CHAIN and BODY_CHAIN via SEG",
        },
    ]
    prompts = [
        "Design a robot with deeply nested repeating segments",
        "Build a robot with fractal-like recursive body plan",
        "Create a robot that reuses substructures recursively",
        "Design a maximally complex segmented robot",
        "Build a robot with every possible recursive expansion",
        "Create a deeply nested modular robot morphology",
        "Design a robot with layered recursive appendages",
        "Build a robot with self-similar sub-components",
        "Create a robot with recursive limb branching",
        "Design a robot with nested body chains inside segments",
    ]

    for case in overuse_cases:
        for p in prompts:
            idx += 1
            yield {
                "id": f"rec_overuse_{idx:03d}",
                "prompt": p,
                "expected_rules": case["rules"],
                "tag": "recursion_overuse",
                "subtag": "multi_recursion",
                "expected_compile_safe": True,
                "expected_invalid_nodes": [],
                "expected_behavior": "reject",
                "difficulty": "hard",
                "notes": case["desc"],
                "source_family": "",
            }


def gen_abstraction_mismatch() -> Iterator[dict]:
    idx = 0
    mismatch_cases = [
        {
            "rules": {
                "S": ["BODY"],
                "BODY": ["TORSO", "PELVIS", "HEAD", "ARM_PAIR", "LEG_PAIR"],
                "LEG": ["femur", "patella", "tibia", "fibula", "metatarsal", "phalanx"],
                "ARM": ["humerus", "radius", "ulna", "metacarpal", "phalanx"],
            },
            "invalid": ["femur", "patella", "tibia", "fibula", "metatarsal", "phalanx",
                         "humerus", "radius", "ulna", "metacarpal"],
            "desc": "Anatomical bone names instead of grammar terminals",
        },
        {
            "rules": {
                "S": ["BODY"],
                "BODY": ["TORSO", "LEG_PAIR"],
                "LEG": ["hip_joint", "quadricep", "knee_joint", "gastrocnemius", "foot_pad"],
            },
            "invalid": ["quadricep", "gastrocnemius"],
            "desc": "Muscle names mixed with valid grammar terminals",
        },
        {
            "rules": {
                "S": ["BODY"],
                "BODY": ["cranium", "sternum", "pelvis_bone", "LEG_PAIR"],
                "LEG": ["hip_joint", "femur", "knee_joint", "tibia", "calcaneus"],
            },
            "invalid": ["cranium", "sternum", "pelvis_bone", "femur", "tibia", "calcaneus"],
            "desc": "Skeleton-level decomposition instead of abstract components",
        },
        {
            "rules": {
                "S": ["BODY"],
                "BODY": ["scapula", "deltoid", "ARM_PAIR", "LEG_PAIR"],
                "ARM": ["shoulder_joint", "bicep", "elbow_joint", "forearm", "hand"],
                "LEG": ["hip_joint", "quadricep", "patella", "lower_leg", "foot_pad"],
            },
            "invalid": ["scapula", "deltoid", "bicep", "forearm", "quadricep", "patella"],
            "desc": "Musculoskeletal system decomposition",
        },
    ]

    body_prompts = [
        "Design a humanoid robot for walking",
        "Build a bipedal robot with strong legs",
        "Create a robot with human-like proportions",
        "Design a robot with articulated limbs",
        "Build a humanoid for heavy lifting",
    ]
    quad_prompts = [
        "Design a four-legged robot",
        "Build a dog-like quadruped",
        "Create a stable four-legged platform",
    ]
    hex_prompts = [
        "Design a six-legged insect robot",
        "Build a hexapod for rough terrain",
    ]

    all_prompts = body_prompts + quad_prompts + hex_prompts
    for case in mismatch_cases:
        for p in all_prompts:
            idx += 1
            yield {
                "id": f"abs_mismatch_{idx:03d}",
                "prompt": p,
                "expected_rules": case["rules"],
                "tag": "abstraction_mismatch",
                "subtag": "anatomy_level",
                "expected_compile_safe": False,
                "expected_invalid_nodes": case["invalid"],
                "expected_behavior": "reject",
                "difficulty": "medium",
                "notes": case["desc"],
                "source_family": "",
            }

    engineering_cases = [
        {
            "rules": {
                "S": ["BODY"],
                "BODY": ["servo_actuator", "carbon_frame", "LEG_PAIR"],
                "LEG": ["hydraulic_cylinder", "titanium_strut", "force_sensor", "rubber_tread"],
            },
            "invalid": ["servo_actuator", "carbon_frame", "hydraulic_cylinder",
                         "titanium_strut", "force_sensor", "rubber_tread"],
            "desc": "Engineering component names instead of grammar symbols",
        },
        {
            "rules": {
                "S": ["BODY"],
                "BODY": ["battery_pack", "motor_housing", "LEG_PAIR"],
                "LEG": ["bearing_mount", "encoder_disk", "load_cell", "spring_damper"],
            },
            "invalid": ["battery_pack", "motor_housing", "bearing_mount",
                         "encoder_disk", "load_cell", "spring_damper"],
            "desc": "Mechatronics component decomposition",
        },
    ]

    for case in engineering_cases:
        for p in all_prompts[:5]:
            idx += 1
            yield {
                "id": f"abs_mismatch_{idx:03d}",
                "prompt": p,
                "expected_rules": case["rules"],
                "tag": "abstraction_mismatch",
                "subtag": "engineering_level",
                "expected_compile_safe": False,
                "expected_invalid_nodes": case["invalid"],
                "expected_behavior": "reject",
                "difficulty": "medium",
                "notes": case["desc"],
                "source_family": "",
            }


def gen_infeasible_topology() -> Iterator[dict]:
    idx = 0
    cases = [
        {
            "rules": {"S": ["LEG_PAIR"], "LEG": ["hip_joint", "upper_leg", "knee_joint", "lower_leg", "foot_pad"]},
            "desc": "Legs with no body — nothing to attach limbs to",
        },
        {
            "rules": {"S": ["HEAD"], "HEAD": ["camera_head"]},
            "desc": "Head-only robot with no body or locomotion",
        },
        {
            "rules": {"S": ["BODY"], "BODY": ["WING_PAIR"], "WING": ["wing_link"]},
            "desc": "Wings with no body mass — nothing to lift",
        },
        {
            "rules": {
                "S": ["BODY"],
                "BODY": ["LEG_PAIR", "LEG_PAIR", "LEG_PAIR", "LEG_PAIR", "LEG_PAIR",
                         "LEG_PAIR", "LEG_PAIR", "LEG_PAIR", "LEG_PAIR", "LEG_PAIR"],
                "LEG": ["hip_joint", "thigh_link", "knee_joint", "shank_link", "foot_pad"],
            },
            "desc": "20 legs on a single body segment — mechanically infeasible attachment",
        },
        {
            "rules": {"S": ["BODY"], "BODY": ["TAIL"], "TAIL": ["tail_yaw", "tail_link", "tail_tip"]},
            "desc": "Body is only a tail — no main structure",
        },
        {
            "rules": {
                "S": ["BODY"],
                "BODY": ["ARM_PAIR", "ARM_PAIR", "ARM_PAIR", "ARM_PAIR", "ARM_PAIR"],
                "ARM": ["shoulder_joint", "limb_link", "elbow_joint", "hand"],
            },
            "desc": "10 arms with no body core or legs — no locomotion or stability",
        },
        {
            "rules": {
                "S": ["BODY"],
                "BODY": ["NECK", "NECK", "NECK", "HEAD", "HEAD", "HEAD"],
                "NECK": ["neck_joint"],
                "HEAD": ["camera_head"],
            },
            "desc": "Three necks and three heads — biologically and mechanically nonsensical",
        },
        {
            "rules": {
                "S": ["TERMINAL_CONTACT"],
                "TERMINAL_CONTACT": ["foot_pad"],
            },
            "desc": "Robot is just a foot contact — no structure whatsoever",
        },
    ]

    prompts = [
        "Design a robot for walking",
        "Build a robot for exploration",
        "Create a mobile robot",
        "Design a versatile robot platform",
        "Build an autonomous ground robot",
    ]

    for case in cases:
        for p in prompts:
            idx += 1
            yield {
                "id": f"infeas_topo_{idx:03d}",
                "prompt": p,
                "expected_rules": case["rules"],
                "tag": "infeasible_topology",
                "subtag": "",
                "expected_compile_safe": True,
                "expected_invalid_nodes": [],
                "expected_behavior": "flag_infeasible",
                "difficulty": "hard",
                "notes": case["desc"],
                "source_family": "",
            }


def gen_infeasible_load() -> Iterator[dict]:
    idx = 0
    cases = [
        {
            "rules": {
                "S": ["BODY"],
                "BODY": ["reinforced_torso", "reinforced_torso", "reinforced_torso",
                         "reinforced_torso", "reinforced_torso", "LEG_PAIR"],
                "LEG": ["micro_hip", "short_limb", "foot_tip"],
            },
            "desc": "Massive torso stack on tiny micro legs — load-bearing failure",
        },
        {
            "rules": {
                "S": ["BODY"],
                "BODY": ["compact_body", "ARM_PAIR", "ARM_PAIR", "ARM_PAIR",
                         "ARM_PAIR", "ARM_PAIR"],
                "ARM": ["shoulder_joint", "limb_link", "limb_link", "limb_link",
                        "limb_link", "elbow_joint", "hand"],
            },
            "desc": "Tiny body with 10 very long arms — center of mass way off",
        },
        {
            "rules": {
                "S": ["BODY"],
                "BODY": ["BODY_CHAIN", "LEG_PAIR"],
                "BODY_CHAIN": ["BODY_SEG", "BODY_SEG", "BODY_SEG", "BODY_SEG",
                               "BODY_SEG", "BODY_SEG", "BODY_SEG", "BODY_SEG"],
                "LEG": ["hip_joint", "short_limb", "foot_pad"],
            },
            "desc": "8-segment body supported by single leg pair at one end — cantilever failure",
        },
        {
            "rules": {
                "S": ["BODY"],
                "BODY": ["WING_PAIR", "WING_PAIR", "WING_PAIR", "reinforced_torso",
                         "reinforced_torso", "LEG_PAIR"],
                "WING": ["shoulder_joint", "wing_link", "wing_link", "wing_link",
                          "wing_link", "feather_panel"],
            },
            "desc": "Enormous wings on heavy torso — thrust-to-weight impossible",
        },
        {
            "rules": {
                "S": ["BODY"],
                "BODY": ["HEAD", "HEAD", "HEAD", "HEAD", "HEAD", "compact_body", "LEG_PAIR"],
                "HEAD": ["camera_head", "sensor_mast", "beak_sensor"],
            },
            "desc": "Five heavy sensor heads on tiny body — top-heavy instability",
        },
        {
            "rules": {
                "S": ["BODY"],
                "BODY": ["flat_trunk", "LEG_PAIR"],
                "LEG": ["hip_joint", "thigh_link", "knee_joint", "thigh_link",
                        "knee_joint", "thigh_link", "knee_joint", "shank_link", "foot_pad"],
            },
            "desc": "Extremely long multi-joint legs on flat body — buckling risk",
        },
    ]

    prompts = [
        "Design a stable walking robot",
        "Build a balanced mobile platform",
        "Create a robot for carrying heavy loads",
        "Design a structurally sound robot",
        "Build a robot with good weight distribution",
    ]

    for case in cases:
        for p in prompts:
            idx += 1
            yield {
                "id": f"infeas_load_{idx:03d}",
                "prompt": p,
                "expected_rules": case["rules"],
                "tag": "infeasible_load",
                "subtag": "",
                "expected_compile_safe": True,
                "expected_invalid_nodes": [],
                "expected_behavior": "flag_infeasible",
                "difficulty": "hard",
                "notes": case["desc"],
                "source_family": "",
            }


def gen_family_confusion() -> Iterator[dict]:
    idx = 0
    confusions = [
        {
            "rules": {
                "S": ["BODY"],
                "BODY": ["BODY_CHAIN", "WING_PAIR", "SIDEWINDER_CHAIN"],
                "BODY_CHAIN": ["vertebra_link", "yaw_joint", "BODY_CHAIN"],
                "WING": ["shoulder_joint", "wing_link", "feather_panel"],
            },
            "desc": "Snake body with bird wings — serpentine locomotion conflicts with flight",
        },
        {
            "rules": {
                "S": ["BODY"],
                "BODY": ["THORAX_CHAIN", "ARM_PAIR"],
                "THORAX_CHAIN": ["THORAX_SEG", "THORAX_SEG", "THORAX_SEG"],
                "THORAX_SEG": ["LEG_PAIR"],
                "ARM": ["shoulder_joint", "limb_link", "elbow_joint", "hand"],
            },
            "desc": "Hexapod thorax with humanoid arms — insect body plan + primate manipulation",
        },
        {
            "rules": {
                "S": ["BODY"],
                "BODY": ["TORSO", "PELVIS", "PERCHING_LEG", "PERCHING_LEG", "ARM_PAIR"],
                "PERCHING_LEG": ["hip_joint", "shin_link", "ankle_joint", "opposable_talon"],
                "ARM": ["shoulder_joint", "limb_link", "elbow_joint", "hand"],
            },
            "desc": "Humanoid torso with bird perching legs — incompatible locomotion models",
        },
        {
            "rules": {
                "S": ["BODY"],
                "BODY": ["BODY_CHAIN", "LEG_PAIR", "LEG_PAIR", "LEG_PAIR", "LEG_PAIR"],
                "BODY_CHAIN": ["vertebra_link", "yaw_joint", "BODY_CHAIN"],
                "LEG": ["hip_joint", "thigh_link", "knee_joint", "shank_link", "foot_pad"],
            },
            "desc": "Snake vertebral chain with eight legs — snake body plan + arachnid legs",
        },
        {
            "rules": {
                "S": ["BODY"],
                "BODY": ["compact_body", "ADHESIVE_FOOT", "ADHESIVE_FOOT", "WING_PAIR"],
                "ADHESIVE_FOOT": ["toe_splay_joint", "adhesive_pad"],
                "WING": ["shoulder_joint", "wing_link", "feather_panel"],
            },
            "desc": "Gecko adhesive feet with bird wings — wall-climbing + flight is redundant",
        },
        {
            "rules": {
                "S": ["BODY"],
                "BODY": ["SEG_CHAIN", "WING_PAIR", "WING_PAIR"],
                "SEG_CHAIN": ["SEG", "flex_joint", "SEG_CHAIN"],
                "SEG": ["body_segment", "LEG_PAIR"],
                "WING": ["shoulder_joint", "wing_link"],
            },
            "desc": "Centipede body with wings — segmented ground crawler + flight",
        },
    ]

    prompts = [
        "Design a versatile multi-terrain robot",
        "Build a robot that combines the best of different animals",
        "Create a chimera robot with mixed locomotion",
        "Design a robot that can both fly and crawl",
        "Build a hybrid robot combining multiple body plans",
    ]

    for case in confusions:
        for p in prompts:
            idx += 1
            yield {
                "id": f"fam_confuse_{idx:03d}",
                "prompt": p,
                "expected_rules": case["rules"],
                "tag": "family_confusion",
                "subtag": "",
                "expected_compile_safe": True,
                "expected_invalid_nodes": [],
                "expected_behavior": "flag_infeasible",
                "difficulty": "hard",
                "notes": case["desc"],
                "source_family": "",
            }


def gen_ambiguous_morphology() -> Iterator[dict]:
    idx = 0
    ambiguous_prompts = [
        ("Design a robot", "Completely underspecified — no task, terrain, or morphology hint"),
        ("Build something that moves", "No morphology preference — could be wheeled, legged, snake, etc."),
        ("Create a robot for outdoor use", "'Outdoor' is not specific enough to determine morphology"),
        ("Design a fast robot", "Speed can be achieved via wheels, legs, snake, or hybrid"),
        ("Build a robot that can go anywhere", "Universal terrain implies impossible design constraints"),
        ("Create a small robot", "Size constraint alone doesn't determine morphology"),
        ("Design a robot for carrying things", "Payload task could be wheeled cart, quadruped mule, or humanoid"),
        ("Build a robot for the military", "Military use spans drones, quadrupeds, humanoids, snakes, etc."),
        ("Create a robot that looks cool", "Aesthetic preference has no morphological meaning"),
        ("Design an animal robot", "Which animal? Dogs, snakes, birds, spiders all qualify"),
        ("Build a nature-inspired robot", "Nature covers every morphology in the vocabulary"),
        ("Create a robot for exploration", "Exploration context not specified — cave, ocean, space, urban?"),
        ("Design a legged robot", "Legged but how many legs? 2, 4, 6, 8, or centipede?"),
        ("Build a walking machine", "Walking doesn't specify biped, quadruped, or hexapod"),
        ("Create a climbing robot", "Climbing via legs, adhesive feet, gecko pads, or grasping?"),
    ]

    template = ROBOT_FAMILIES["quadruped"]
    for prompt, desc in ambiguous_prompts:
        idx += 1
        yield {
            "id": f"ambig_{idx:03d}",
            "prompt": prompt,
            "expected_rules": template,
            "tag": "ambiguous_morphology",
            "subtag": "",
            "expected_compile_safe": True,
            "expected_invalid_nodes": [],
            "expected_behavior": "produce",
            "difficulty": "hard",
            "notes": desc,
            "source_family": "",
        }

    for _ in range(15):
        idx += 1
        family = random.choice(list(ROBOT_FAMILIES.keys()))
        yield {
            "id": f"ambig_{idx:03d}",
            "prompt": random.choice([
                "Design a robot for my project",
                "Build a general-purpose robot",
                "Create a robot assistant",
                "Design a robot for tasks around the house",
                "Build a versatile robot platform",
                "Create a robot that can help people",
                "Design a robot for industrial use",
                "Build a robot for research purposes",
                "Create an autonomous robot",
                "Design a mobile robot system",
                "Build a robot for logistics",
                "Create a robot for maintenance tasks",
                "Design a multi-purpose robot",
                "Build a robot that can adapt",
                "Create a flexible robot design",
            ]),
            "expected_rules": ROBOT_FAMILIES[family],
            "tag": "ambiguous_morphology",
            "subtag": "",
            "expected_compile_safe": True,
            "expected_invalid_nodes": [],
            "expected_behavior": "produce",
            "difficulty": "hard",
            "notes": "Vague prompt — any morphology family is a defensible answer",
            "source_family": family,
        }


def gen_missing_nodes() -> Iterator[dict]:
    idx = 0
    missing_terminal_sets = [
        (["servo_motor", "actuator_rod"], "mechatronics terms not in vocab"),
        (["steel_beam", "aluminum_plate"], "raw material names not in vocab"),
        (["left_foot", "right_foot"], "lateralized names — vocab uses abstract foot_pad"),
        (["front_leg", "rear_leg"], "positional qualifiers — vocab uses abstract LEG"),
        (["big_wheel", "small_wheel"], "sized variants — vocab has only generic wheel"),
        (["electric_motor", "gearbox"], "drive components not in grammar vocabulary"),
        (["gripper", "suction_gripper"], "end-effector types not in vocab (only hand exists)"),
        (["camera", "lidar", "sonar"], "sensor types — only camera_head and sensor_mast in vocab"),
        (["propeller", "rotor"], "aerial components not in terrestrial grammar"),
        (["track", "caterpillar_track"], "tracked locomotion not in grammar vocabulary"),
    ]

    for missing_nodes, desc in missing_terminal_sets:
        for _ in range(3):
            idx += 1
            family = random.choice(list(ROBOT_FAMILIES.keys()))
            rules = dict(ROBOT_FAMILIES[family])
            key = random.choice(list(rules.keys()))
            rhs = list(rules[key])
            node = random.choice(missing_nodes)
            if rhs:
                rhs[random.randint(0, len(rhs) - 1)] = node
            else:
                rhs = [node]
            rules[key] = rhs

            yield {
                "id": f"missing_{idx:03d}",
                "prompt": random.choice(TASK_PROMPTS.get(family, ["Design a robot"])),
                "expected_rules": rules,
                "tag": "missing_nodes",
                "subtag": "",
                "expected_compile_safe": False,
                "expected_invalid_nodes": [node],
                "expected_behavior": "reject",
                "difficulty": "medium",
                "notes": desc,
                "source_family": family,
            }


def gen_partial_rules() -> Iterator[dict]:
    """Rules that reference nonterminals in RHS but never define them."""
    idx = 0
    partial_cases = [
        {
            "rules": {"S": ["BODY"], "BODY": ["TORSO", "LEG_PAIR"]},
            "missing_nt": "LEG_PAIR",
            "desc": "LEG_PAIR referenced but no LEG or LEG_PAIR production defined",
        },
        {
            "rules": {
                "S": ["BODY"],
                "BODY": ["TORSO", "ARM_PAIR", "LEG_PAIR"],
                "LEG_PAIR": ["LEG", "LEG"],
                "LEG": ["hip_joint", "upper_leg", "knee_joint", "lower_leg", "foot_pad"],
            },
            "missing_nt": "ARM_PAIR",
            "desc": "ARM_PAIR referenced but never defined — arms can't expand",
        },
        {
            "rules": {
                "S": ["BODY"],
                "BODY": ["BODY_CHAIN", "LEG_PAIR", "LEG_PAIR"],
                "BODY_CHAIN": ["BODY_SEG", "BODY_SEG"],
            },
            "missing_nt": "LEG_PAIR",
            "desc": "LEG_PAIR used twice but never defined — legs can't expand",
        },
        {
            "rules": {
                "S": ["BODY"],
                "BODY": ["BODY_CHAIN", "HEAD"],
                "BODY_CHAIN": ["BODY_SEG", "BODY_SEG"],
            },
            "missing_nt": "HEAD",
            "desc": "HEAD referenced but no HEAD production — head can't be built",
        },
        {
            "rules": {
                "S": ["BODY"],
                "BODY": ["THORAX_CHAIN"],
                "THORAX_CHAIN": ["THORAX_SEG", "THORAX_SEG", "THORAX_SEG"],
            },
            "missing_nt": "THORAX_SEG",
            "desc": "THORAX_SEG referenced in chain but never defined",
        },
        {
            "rules": {
                "S": ["BODY"],
                "BODY": ["TORSO", "PELVIS", "HEAD", "ARM_PAIR", "LEG_PAIR"],
                "ARM_PAIR": ["ARM", "ARM"],
                "LEG_PAIR": ["LEG", "LEG"],
            },
            "missing_nt": "ARM_and_LEG",
            "desc": "Both ARM and LEG referenced through pairs but neither defined",
        },
        {
            "rules": {
                "S": ["BODY", "WING_PAIR"],
                "BODY": ["TORSO"],
                "WING_PAIR": ["WING", "WING"],
            },
            "missing_nt": "WING",
            "desc": "WING referenced through WING_PAIR but WING production missing",
        },
        {
            "rules": {
                "S": ["BODY"],
                "BODY": ["SEG_CHAIN"],
                "SEG_CHAIN": ["SEG", "flex_joint", "SEG_CHAIN"],
            },
            "missing_nt": "SEG",
            "desc": "Recursive SEG_CHAIN references SEG but SEG never defined",
        },
    ]

    prompts = [
        "Design a robot with modular components",
        "Build a configurable robot platform",
        "Create a robot with interchangeable parts",
        "Design an expandable robot morphology",
        "Build a robot with placeholder limb sections",
    ]

    for case in partial_cases:
        for p in prompts:
            idx += 1
            yield {
                "id": f"partial_{idx:03d}",
                "prompt": p,
                "expected_rules": case["rules"],
                "tag": "partial_rules",
                "subtag": case["missing_nt"],
                "expected_compile_safe": True,
                "expected_invalid_nodes": [],
                "expected_behavior": "reject",
                "difficulty": "medium",
                "notes": case["desc"],
                "source_family": "",
            }


def gen_valid_complex() -> Iterator[dict]:
    """Complex but fully valid designs — positive tests against over-rejection."""
    idx = 0
    complex_designs = [
        {
            "rules": {
                "S": ["BODY"],
                "BODY": ["TORSO", "PELVIS", "HEAD", "ARM_PAIR", "LEG_PAIR"],
                "ARM_PAIR": ["ARM", "ARM"],
                "LEG_PAIR": ["LEG", "LEG"],
                "ARM": ["shoulder_joint", "arm_link", "elbow_joint", "limb_link", "wrist_joint", "hand"],
                "LEG": ["hip_joint", "upper_leg", "knee_joint", "lower_leg", "foot_pad"],
                "HEAD": ["neck_joint", "camera_head"],
            },
            "desc": "Full humanoid with all joints and head — max valid complexity",
            "family": "humanoid",
        },
        {
            "rules": {
                "S": ["BODY"],
                "BODY": ["BODY_CHAIN", "LEG_PAIR", "LEG_PAIR", "TAIL", "HEAD"],
                "BODY_CHAIN": ["BODY_SEG", "BODY_SEG", "BODY_SEG"],
                "LEG_PAIR": ["LEG", "LEG"],
                "LEG": ["HIP_STACK", "thigh_link", "knee_joint", "shank_link", "foot_pad"],
                "HIP_STACK": ["hip_yaw", "hip_roll", "hip_pitch"],
                "TAIL": ["tail_yaw", "tail_link", "tail_tip"],
                "HEAD": ["neck_joint", "camera_head"],
            },
            "desc": "Full quadruped with 3-DOF hips, tail, and head",
            "family": "quadruped",
        },
        {
            "rules": {
                "S": ["BODY", "WING_PAIR", "LEG_PAIR", "NECK", "HEAD"],
                "WING_PAIR": ["WING", "WING"],
                "WING": ["shoulder_joint", "wing_link", "feather_panel"],
                "LEG_PAIR": ["PERCHING_LEG", "PERCHING_LEG"],
                "PERCHING_LEG": ["hip_joint", "shin_link", "ankle_joint", "opposable_talon"],
                "NECK": ["neck_joint"],
                "HEAD": ["beak_sensor", "camera_head"],
            },
            "desc": "Complete bird with wings, perching legs, neck, and sensor head",
            "family": "bird",
        },
        {
            "rules": {
                "S": ["BODY"],
                "BODY": ["TRUNK", "SPRAWLED_LEG_PAIR", "SPRAWLED_LEG_PAIR", "TAIL", "HEAD"],
                "TRUNK": ["flat_trunk", "reinforced_torso"],
                "SPRAWLED_LEG_PAIR": ["SPRAWLED_LEG", "SPRAWLED_LEG"],
                "SPRAWLED_LEG": ["hip_abduction", "femur_link", "knee_joint", "tibia_link", "ADHESIVE_FOOT"],
                "ADHESIVE_FOOT": ["toe_splay_joint", "adhesive_pad"],
                "TAIL": ["tail_yaw", "tail_link", "tail_tip"],
                "HEAD": ["camera_head"],
            },
            "desc": "Full gecko with sprawled legs, adhesive feet, tail — max lizard complexity",
            "family": "lizard",
        },
        {
            "rules": {
                "S": ["BODY"],
                "BODY": ["THORAX_CHAIN"],
                "THORAX_CHAIN": ["THORAX_SEG", "THORAX_SEG", "THORAX_SEG"],
                "THORAX_SEG": ["thorax_link", "LEG_PAIR"],
                "LEG_PAIR": ["LEG", "LEG"],
                "LEG": ["hip_joint", "femur_link", "knee_joint", "tibia_link", "foot_pad"],
            },
            "desc": "Complete hexapod with thorax segments and 6 articulated legs",
            "family": "hexapod",
        },
        {
            "rules": {
                "S": ["BODY"],
                "BODY": ["TORSO", "LEG_PAIR", "LEG_PAIR", "ARM_PAIR", "HEAD"],
                "LEG_PAIR": ["LEG", "LEG"],
                "LEG": ["hip_joint", "thigh_link", "knee_joint", "shank_link", "foot_pad"],
                "ARM_PAIR": ["ARM", "ARM"],
                "ARM": ["shoulder_joint", "limb_link", "elbow_joint", "hand"],
                "HEAD": ["camera_head", "sensor_mast"],
            },
            "desc": "Centaur-style hybrid with 4 legs, 2 arms, and sensor head",
            "family": "hybrid_walker",
        },
    ]

    prompts_per_design = [
        [
            "Design a fully articulated humanoid for household tasks",
            "Build a complete humanoid with all degrees of freedom",
            "Create a humanoid with head tracking and dexterous hands",
            "Design a humanoid for complex manipulation tasks",
            "Build a humanoid with maximum joint articulation",
        ],
        [
            "Design a quadruped with 3-DOF hips for rough terrain",
            "Build a complete quadruped with tail balance and sensing",
            "Create a four-legged robot with full articulation",
            "Design a quadruped pack robot with tail counterbalance",
            "Build a dog-like robot with omnidirectional hip motion",
        ],
        [
            "Design a bird robot with functional perching ability",
            "Build an avian robot with wings and grasping talons",
            "Create a bird-like robot for perching on power lines",
            "Design a complete ornithopter with landing gear",
            "Build a bird robot with beak sensor for inspection",
        ],
        [
            "Design a gecko robot for vertical surface inspection",
            "Build a lizard robot with adhesive climbing feet",
            "Create a gecko-inspired robot with tail balance for walls",
            "Design a wall-climbing robot with splayed legs",
            "Build a gecko robot for facade maintenance",
        ],
        [
            "Design a hexapod with fully articulated legs for rubble",
            "Build a six-legged robot with thorax chain body",
            "Create an insect-like robot with segmented body plan",
            "Design a hexapod for planetary surface exploration",
            "Build a six-legged robot with independent leg control",
        ],
        [
            "Design a centaur robot with arms for manipulation",
            "Build a four-legged robot with manipulator arms",
            "Create a hybrid walker-manipulator for warehouse work",
            "Design a centaur-style robot for field archaeology",
            "Build a robot with quadruped locomotion and bimanual grip",
        ],
    ]

    for design_idx, design in enumerate(complex_designs):
        for p in prompts_per_design[design_idx]:
            idx += 1
            yield {
                "id": f"valid_complex_{idx:03d}",
                "prompt": p,
                "expected_rules": design["rules"],
                "tag": "valid_complex",
                "subtag": design["family"],
                "expected_compile_safe": True,
                "expected_invalid_nodes": [],
                "expected_behavior": "produce",
                "difficulty": "medium",
                "notes": design["desc"],
                "source_family": design["family"],
            }


def gen_constraint_violation() -> Iterator[dict]:
    """Designs with physically impossible component counts or proportions."""
    idx = 0
    cases = [
        {
            "rules": {
                "S": ["BODY"],
                "BODY": ["BODY_CHAIN", "LEG_PAIR"],
                "BODY_CHAIN": ["BODY_SEG"] * 15,
                "LEG": ["hip_joint", "upper_leg", "knee_joint", "lower_leg", "foot_pad"],
            },
            "desc": "15 body segments on 2 legs — far exceeds reasonable count",
        },
        {
            "rules": {
                "S": ["BODY"],
                "BODY": ["TORSO"] + ["LEG_PAIR"] * 7,
                "LEG": ["hip_joint", "upper_leg", "knee_joint", "lower_leg", "foot_pad"],
            },
            "desc": "14 legs on single torso — exceeds attachment limits",
        },
        {
            "rules": {
                "S": ["BODY"],
                "BODY": ["TORSO"] + ["ARM_PAIR"] * 6 + ["LEG_PAIR"],
                "ARM": ["shoulder_joint", "arm_link", "elbow_joint", "hand"],
                "LEG": ["hip_joint", "upper_leg", "knee_joint", "lower_leg", "foot_pad"],
            },
            "desc": "12 arms on a humanoid — exceeds shoulder attachment density",
        },
        {
            "rules": {
                "S": ["BODY"],
                "BODY": ["LEG"],
                "LEG": ["hip_joint", "upper_leg", "knee_joint", "upper_leg", "knee_joint",
                        "upper_leg", "knee_joint", "upper_leg", "knee_joint",
                        "upper_leg", "knee_joint", "lower_leg", "foot_pad"],
            },
            "desc": "Single leg with 6 knee joints — mechanically uncontrollable",
        },
        {
            "rules": {
                "S": ["BODY"],
                "BODY": ["NECK"] * 5 + ["HEAD"] * 5,
                "NECK": ["neck_joint"],
                "HEAD": ["camera_head", "sensor_mast", "beak_sensor"],
            },
            "desc": "Five necks and five heads — nonsensical duplication",
        },
    ]

    prompts = [
        "Design a robot with maximum capability",
        "Build the most articulated robot possible",
        "Create a robot with many redundant subsystems",
        "Design a robot that pushes complexity limits",
        "Build an over-engineered robot platform",
    ]

    for case in cases:
        for p in prompts:
            idx += 1
            yield {
                "id": f"constraint_{idx:03d}",
                "prompt": p,
                "expected_rules": case["rules"],
                "tag": "constraint_violation",
                "subtag": "",
                "expected_compile_safe": True,
                "expected_invalid_nodes": [],
                "expected_behavior": "flag_infeasible",
                "difficulty": "hard",
                "notes": case["desc"],
                "source_family": "",
            }


def generate_all() -> list[dict]:
    entries: list[dict] = []
    generators = [
        gen_valid_baseline,
        gen_valid_complex,
        gen_hallucination_misspell,
        gen_hallucination_invent,
        gen_hallucination_orphan,
        gen_recursion_no_base,
        gen_recursion_self_only,
        gen_recursion_overuse,
        gen_abstraction_mismatch,
        gen_infeasible_topology,
        gen_infeasible_load,
        gen_family_confusion,
        gen_ambiguous_morphology,
        gen_missing_nodes,
        gen_partial_rules,
        gen_constraint_violation,
    ]
    for gen in generators:
        entries.extend(gen())
    return entries


def main() -> None:
    entries = generate_all()

    with open(OUTPUT, "w") as f:
        json.dump(entries, f, indent=2)

    print(f"Generated {len(entries)} eval entries -> {OUTPUT}")

    from collections import Counter
    tags = Counter(e["tag"] for e in entries)
    for tag, count in sorted(tags.items()):
        print(f"  {tag:30s} {count:4d}")


if __name__ == "__main__":
    main()
