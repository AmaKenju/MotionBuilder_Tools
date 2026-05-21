# -*- coding: utf-8 -*-
# Compatible with both Python 2.7 (MotionBuilder <=2019) and Python 3.7+ (MotionBuilder 2022+).
from pyfbsdk import (
    FBFindModelByLabelName,
    FBModelNull,
    FBModelSkeleton,
    FBModelMarker,
    FBSystem,
    FBConstraintRelation,
    FBConnect,
    FBColor,
)


TARGET_NAME = "Vicon:Optical"
NEW_ROOT_NAME = "Vicon:Optical_copy"
MARKERS_ROOT_NAME = "Vicon:Optical_copy_OffsetMarkers"
RELATION_NAME = "Vicon_Optical_copy_Relation"

CLONE_BONE_COLOR = FBColor(1.0, 0.2, 0.2)
MARKER_COLOR = FBColor(0.1, 0.9, 1.0)

ADD_BOX_CANDIDATES = [
    ("Vector", "Add (V1 + V2)"),
    ("Vector", "Add"),
    ("Number", "Add (V1 + V2)"),
    ("Number", "Add"),
    ("Other", "Add (V1 + V2)"),
    ("Other", "Add"),
    ("Number", "Add (a + b)"),
]


def safe_long_name(component):
    try:
        return getattr(component, "LongName", "") or ""
    except UnicodeDecodeError:
        return ""


def collect_existing_namespaces():
    existing = set()
    for c in FBSystem().Scene.Components:
        ln = safe_long_name(c)
        if ":" in ln:
            existing.add(ln.split(":", 1)[0])
    return existing


def collect_existing_long_names():
    names = set()
    for c in FBSystem().Scene.Components:
        ln = safe_long_name(c)
        if ln:
            names.add(ln)
    return names


def make_unique(base, existing):
    if base not in existing:
        existing.add(base)
        return base
    i = 1
    while True:
        candidate = "{0}{1}".format(base, i)
        if candidate not in existing:
            existing.add(candidate)
            return candidate
        i += 1


def split_namespace(long_name):
    if ":" in long_name:
        ns, short = long_name.split(":", 1)
        return ns, short
    return "", long_name


def clone_hierarchy(model, new_parent, target_namespace, pairs):
    clone = model.Clone()
    if clone is None:
        return None
    clone.Parent = new_parent

    _, short = split_namespace(model.LongName)
    clone.LongName = "{0}:{1}".format(target_namespace, short)

    if isinstance(clone, FBModelSkeleton):
        clone.Color = CLONE_BONE_COLOR

    pairs.append((model, clone))

    for child in list(model.Children):
        clone_hierarchy(child, clone, target_namespace, pairs)
    return clone


def duplicate_children_under_new_root(parent_name, new_root_name):
    parent = FBFindModelByLabelName(parent_name)
    if parent is None:
        raise RuntimeError("Node not found: {0}".format(parent_name))

    existing_long_names = collect_existing_long_names()
    existing_namespaces = collect_existing_namespaces()

    unique_root_name = make_unique(new_root_name, existing_long_names)
    new_root_ns, new_root_short = split_namespace(unique_root_name)

    new_root = FBModelNull(new_root_short)
    if new_root_ns:
        new_root.LongName = "{0}:{1}".format(new_root_ns, new_root_short)
    new_root.Show = True

    pairs = []
    for child in list(parent.Children):
        base_ns, _ = split_namespace(child.LongName)
        if not base_ns:
            base_ns = child.Name
        new_ns = make_unique("{0}_copy".format(base_ns), existing_namespaces)
        clone_hierarchy(child, new_root, new_ns, pairs)

    FBSystem().Scene.Evaluate()
    return new_root, pairs


def find_anim_node(parent_node, *names):
    if parent_node is None:
        return None
    for n in parent_node.Nodes:
        for target in names:
            if n.Name == target:
                return n
    return None


_add_box_path_cache = [None]


def create_add_box(relation):
    if _add_box_path_cache[0] is not None:
        group, name = _add_box_path_cache[0]
        return relation.CreateFunctionBox(group, name)
    for group, name in ADD_BOX_CANDIDATES:
        try:
            box = relation.CreateFunctionBox(group, name)
        except Exception:
            continue
        if box is not None:
            _add_box_path_cache[0] = (group, name)
            return box
    return None


def create_marker_group(existing_long_names):
    unique = make_unique(MARKERS_ROOT_NAME, existing_long_names)
    ns, short = split_namespace(unique)
    grp = FBModelNull(short)
    if ns:
        grp.LongName = "{0}:{1}".format(ns, short)
    grp.Show = True
    return grp


def build_offset_relation(name, pairs):
    """For each skeleton pair, build an Offset Marker + Relation graph:

        src.LclT  ─────────────────────►  dst.LclT
        src.LclR  ──┐
                    Add(V1+V2) ─►  dst.LclR
        marker.LclR ┘

        dst.GlobalT  ──►  marker.GlobalT     (keeps marker aligned with dst)

    Rotating the marker in the viewport injects a per-bone offset rotation
    on top of the source's local rotation.
    """
    skeleton_pairs = [
        (src, dst) for (src, dst) in pairs
        if isinstance(src, FBModelSkeleton) and isinstance(dst, FBModelSkeleton)
    ]

    existing_long_names = collect_existing_long_names()
    marker_group = create_marker_group(existing_long_names)

    relation = FBConstraintRelation(name)
    relation.Active = True

    y_step = 260
    x_src_sender = 0
    x_add = 450
    x_dst_receiver = 900
    x_dst_sender = 0
    x_marker_receiver = 900

    markers = []
    connections = 0
    add_box_failed = False
    diag_done = False

    for index, (src_model, dst_model) in enumerate(skeleton_pairs):
        _, dst_short = split_namespace(dst_model.LongName)
        marker_name = "{0}_offset".format(dst_short)
        marker = FBModelMarker(marker_name)
        marker.Parent = marker_group
        marker.Color = MARKER_COLOR
        marker.Show = True
        markers.append(marker)

        src_sender = relation.SetAsSource(src_model)
        src_sender.UseGlobalTransforms = False

        dst_receiver = relation.ConstrainObject(dst_model)
        dst_receiver.UseGlobalTransforms = False

        marker_sender = relation.SetAsSource(marker)
        marker_sender.UseGlobalTransforms = False

        dst_sender = relation.SetAsSource(dst_model)
        # leave as Global (default) for Translation output

        marker_receiver = relation.ConstrainObject(marker)
        # leave as Global (default) for Translation input

        add_box = create_add_box(relation)
        if add_box is None:
            if not add_box_failed:
                print("ERROR: Could not create an Add function box. "
                      "Tried: {0}".format(ADD_BOX_CANDIDATES))
                add_box_failed = True
            continue

        y = index * y_step
        relation.SetBoxPosition(src_sender, x_src_sender, y)
        relation.SetBoxPosition(marker_sender, x_src_sender, y + 100)
        relation.SetBoxPosition(add_box, x_add, y + 50)
        relation.SetBoxPosition(dst_receiver, x_dst_receiver, y)
        relation.SetBoxPosition(dst_sender, x_dst_sender, y + 170)
        relation.SetBoxPosition(marker_receiver, x_marker_receiver, y + 170)

        src_out = src_sender.AnimationNodeOutGet()
        dst_in = dst_receiver.AnimationNodeInGet()
        marker_out = marker_sender.AnimationNodeOutGet()
        dst_sender_out = dst_sender.AnimationNodeOutGet()
        marker_in = marker_receiver.AnimationNodeInGet()
        add_in = add_box.AnimationNodeInGet()
        add_out = add_box.AnimationNodeOutGet()

        if not diag_done:
            diag_done = True
            print("Add box created via {0}".format(_add_box_path_cache[0]))
            print("  IN nodes:")
            for n in add_in.Nodes:
                print("    - {0}".format(n.Name))
            print("  OUT nodes:")
            for n in add_out.Nodes:
                print("    - {0}".format(n.Name))

        src_lcl_t = find_anim_node(src_out, "Lcl Translation")
        dst_lcl_t = find_anim_node(dst_in, "Lcl Translation")
        if src_lcl_t is not None and dst_lcl_t is not None:
            FBConnect(src_lcl_t, dst_lcl_t)
            connections += 1

        src_lcl_r = find_anim_node(src_out, "Lcl Rotation")
        marker_lcl_r = find_anim_node(marker_out, "Lcl Rotation")
        v1 = find_anim_node(add_in, "V1", "v1", "a", "A")
        v2 = find_anim_node(add_in, "V2", "v2", "b", "B")
        result = find_anim_node(add_out, "Result", "result", "Output", "Out")

        if src_lcl_r is not None and v1 is not None:
            FBConnect(src_lcl_r, v1)
            connections += 1
        if marker_lcl_r is not None and v2 is not None:
            FBConnect(marker_lcl_r, v2)
            connections += 1
        if result is not None:
            dst_lcl_r = find_anim_node(dst_in, "Lcl Rotation")
            if dst_lcl_r is not None:
                FBConnect(result, dst_lcl_r)
                connections += 1

        dst_global_t = find_anim_node(dst_sender_out, "Translation")
        marker_global_t = find_anim_node(marker_in, "Translation")
        if dst_global_t is not None and marker_global_t is not None:
            FBConnect(dst_global_t, marker_global_t)
            connections += 1

    return relation, marker_group, markers, connections


new_root, pairs = duplicate_children_under_new_root(TARGET_NAME, NEW_ROOT_NAME)
print("Created new top-level node: '{0}'".format(new_root.LongName))
print("Total pairs cloned: {0}".format(len(pairs)))

relation, marker_group, markers, connection_count = build_offset_relation(RELATION_NAME, pairs)
print("Marker group: '{0}', markers created: {1}".format(
    marker_group.LongName, len(markers)))
print("Relation '{0}': {1} channel connection(s).".format(
    relation.LongName, connection_count))
