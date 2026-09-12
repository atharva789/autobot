"""Generates G2's four permutation classes (eval-contract.md) from an MJCF schema.

    link_scaled       Scale link lengths 0.5x-2.0x
    limits_altered    Tighten joint limits 40%
    dof_removed       Delete one actuated joint
    topology_swapped  Reparent a subtree

Each function returns a mutated MJCF string, produced by editing the parsed XML tree directly
(not MuJoCo's own spec/compiler API) so the transform is easy to read and to test in isolation
from compilation. The mutant is only valid MJCF if the *input* already loads cleanly -- callers
are expected to feed these the same schema `entity_table.py` and `mujoco_compiler.py` already load
via `mujoco.MjModel.from_xml_path`/`from_xml_string`.

Scope note: these target dev-a.xml's specific body/joint layout (a serial chain rooted at a body
named "base") via named-body defaults, not a schema-agnostic algorithm -- spec.md's four locked
schemas are hand-authored, not generated, so a general "mutate any topology" transform is not
something step 5 needs. A future schema wanting its own permutations calls these with its own
`root_body`/`joint_name`/`subtree`/`new_parent` arguments instead of the defaults.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

_AXES = 3  # x, y, z


class PermutationError(ValueError):
    """Raised when a requested permutation does not apply to the given schema."""


def _parse(xml_text: str) -> ET.ElementTree:
    return ET.ElementTree(ET.fromstring(xml_text))  # noqa: S314 - local, repo-controlled schema


def _serialize(tree: ET.ElementTree) -> str:
    return ET.tostring(tree.getroot(), encoding="unicode")


def _find_body(root: ET.Element, name: str) -> ET.Element:
    for body in root.iter("body"):
        if body.get("name") == name:
            return body
    raise PermutationError(f"no <body name={name!r}> in this schema")


def _find_parent(root: ET.Element, child: ET.Element) -> ET.Element:
    for candidate in root.iter():
        if child in list(candidate):
            return candidate
    raise PermutationError("could not find the parent of the requested element")


def _scale_floats(text: str, factor: float) -> str:
    return " ".join(str(float(v) * factor) for v in text.split())


def link_scaled(xml_text: str, *, factor: float = 1.5, root_body: str = "base") -> str:
    """Scales body offsets and geom size/fromto within `root_body`'s subtree (inclusive).

    `factor` must fall in the contract's 0.5x-2.0x band; 1.0 would not be a permutation at all.
    """

    if not (0.5 <= factor <= 2.0):
        raise PermutationError(f"link_scaled factor {factor} outside eval-contract.md's 0.5-2.0x band")
    if factor == 1.0:
        raise PermutationError("link_scaled factor of 1.0 does not mutate anything")

    tree = _parse(xml_text)
    root = tree.getroot()
    subtree_root = _find_body(root, root_body)

    for body in subtree_root.iter("body"):
        if "pos" in body.attrib:
            body.set("pos", _scale_floats(body.get("pos"), factor))
    for geom in subtree_root.iter("geom"):
        if "size" in geom.attrib:
            geom.set("size", _scale_floats(geom.get("size"), factor))
        if "fromto" in geom.attrib:
            geom.set("fromto", _scale_floats(geom.get("fromto"), factor))

    return _serialize(tree)


def limits_altered(xml_text: str, *, factor: float = 0.6) -> str:
    """Tightens every joint's `range` by scaling both endpoints by `factor` (eval-contract.md:
    "Tighten joint limits 40%" == multiply by 0.6 exactly -- not a free parameter)."""

    tree = _parse(xml_text)
    root = tree.getroot()
    touched = 0
    for joint in root.iter("joint"):
        if "range" in joint.attrib:
            joint.set("range", _scale_floats(joint.get("range"), factor))
            touched += 1
    if touched == 0:
        raise PermutationError("schema has no <joint range=...> to tighten")

    return _serialize(tree)


def dof_removed(xml_text: str, *, joint_name: str = "j_wrist") -> str:
    """Deletes one actuated joint (and its actuator), welding that body rigidly to its parent."""

    tree = _parse(xml_text)
    root = tree.getroot()

    joint = None
    for candidate in root.iter("joint"):
        if candidate.get("name") == joint_name:
            joint = candidate
            break
    if joint is None:
        raise PermutationError(f"no <joint name={joint_name!r}> in this schema")
    _find_parent(root, joint).remove(joint)

    for actuator_parent in root.iter("actuator"):
        for act in list(actuator_parent):
            if act.get("joint") == joint_name:
                actuator_parent.remove(act)

    return _serialize(tree)


def topology_swapped(xml_text: str, *, subtree: str = "finger_left", new_parent: str = "forearm") -> str:
    """Reparents `subtree`'s <body> under `new_parent`, changing every body-relative predicate
    that reads its world position (the parent's frame is now different)."""

    tree = _parse(xml_text)
    root = tree.getroot()

    moved = _find_body(root, subtree)
    old_parent = _find_parent(root, moved)
    new_parent_el = _find_body(root, new_parent)
    if new_parent_el is moved or new_parent_el in list(moved.iter()):
        raise PermutationError(
            f"cannot reparent {subtree!r} under {new_parent!r}: {new_parent!r} is one of "
            f"{subtree!r}'s own descendants, which would create a cycle"
        )

    old_parent.remove(moved)
    new_parent_el.append(moved)

    return _serialize(tree)


PERMUTATION_CLASSES = ("link_scaled", "limits_altered", "dof_removed", "topology_swapped")

_BUILDERS = {
    "link_scaled": link_scaled,
    "limits_altered": limits_altered,
    "dof_removed": dof_removed,
    "topology_swapped": topology_swapped,
}


def build_permutation(xml_text: str, permutation_class: str, **kwargs) -> str:
    if permutation_class not in _BUILDERS:
        raise PermutationError(
            f"unknown permutation class {permutation_class!r}; must be one of {PERMUTATION_CLASSES}"
        )
    return _BUILDERS[permutation_class](xml_text, **kwargs)


__all__ = [
    "PermutationError",
    "PERMUTATION_CLASSES",
    "link_scaled",
    "limits_altered",
    "dof_removed",
    "topology_swapped",
    "build_permutation",
]
