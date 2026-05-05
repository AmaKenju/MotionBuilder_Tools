from pyfbsdk import (
    FBFindModelByLabelName,
    FBModelNull,
    FBModelSkeleton,
    FBSystem,
    FBConstraintRelation,
    FBConnect,
    FBColor,
)


TARGET_NAME = "Vicon:Optical"
NEW_ROOT_NAME = "Vicon:Optical_copy"
RELATION_NAME = "Vicon_Optical_copy_Relation"

CLONE_BONE_COLOR = FBColor(1.0, 0.2, 0.2)


def collect_existing_namespaces():
    existing = set()
    for c in FBSystem().Scene.Components:
        ln = getattr(c, "LongName", "") or ""
        if ":" in ln:
            existing.add(ln.split(":", 1)[0])
    return existing


def collect_existing_long_names():
    names = set()
    for c in FBSystem().Scene.Components:
        ln = getattr(c, "LongName", "") or ""
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


def find_anim_node(parent_node, name):
    if parent_node is None:
        return None
    for n in parent_node.Nodes:
        if n.Name == name:
            return n
    return None


def dump_box(box, label):
    print("--- {0} ({1}) ---".format(label, type(box).__name__ if box else "None"))
    if box is None:
        return
    print("  Properties:")
    for p in box.PropertyList:
        print("    - {0}  ({1})".format(p.Name, type(p).__name__))
    out = box.AnimationNodeOutGet()
    print("  Output animation nodes:")
    if out is not None:
        for n in out.Nodes:
            print("    - {0}".format(n.Name))
    inp = box.AnimationNodeInGet()
    print("  Input animation nodes:")
    if inp is not None:
        for n in inp.Nodes:
            print("    - {0}".format(n.Name))


def set_function_box_source(box, model):
    """Try a few common patterns to assign a source model to a function box."""
    src_prop = box.PropertyList.Find("Source")
    if src_prop is None:
        src_prop = box.PropertyList.Find("Object")
    if src_prop is None:
        return False

    # Try as a list-of-objects property
    try:
        src_prop.append(model)
        return True
    except Exception:
        pass
    # Try as a single-object reference property
    try:
        src_prop.Data = model
        return True
    except Exception:
        pass
    return False


def build_relation_local(name, pairs):
    skeleton_pairs = [
        (src, dst) for (src, dst) in pairs
        if isinstance(src, FBModelSkeleton) and isinstance(dst, FBModelSkeleton)
    ]

    relation = FBConstraintRelation(name)
    relation.Active = True

    y_step = 220
    x_pos_sender = 0
    x_rot_sender = 0
    x_receiver = 700

    diagnostics_printed = False
    connected = 0

    for index, (src_model, dst_model) in enumerate(skeleton_pairs):
        pos_sender = relation.CreateFunctionBox("Senders", "Position")
        rot_sender = relation.CreateFunctionBox("Senders", "Rotation")
        receiver_box = relation.ConstrainObject(dst_model)

        if pos_sender is None or rot_sender is None:
            print("ERROR: Could not create Position/Rotation sender function box.")
            return relation, len(skeleton_pairs), connected

        set_function_box_source(pos_sender, src_model)
        set_function_box_source(rot_sender, src_model)

        y = index * y_step
        relation.SetBoxPosition(pos_sender, x_pos_sender, y)
        relation.SetBoxPosition(rot_sender, x_rot_sender, y + 90)
        relation.SetBoxPosition(receiver_box, x_receiver, y)

        if not diagnostics_printed:
            diagnostics_printed = True
            dump_box(pos_sender, "Position Sender")
            dump_box(rot_sender, "Rotation Sender")
            dump_box(receiver_box, "Receiver model box")

        pos_out = pos_sender.AnimationNodeOutGet()
        rot_out = rot_sender.AnimationNodeOutGet()
        rcv_in = receiver_box.AnimationNodeInGet()

        # Lcl Translation -> receiver Translation (which animates Lcl on the model)
        src_lcl_t = find_anim_node(pos_out, "Lcl Translation")
        dst_t = find_anim_node(rcv_in, "Translation")
        if src_lcl_t is not None and dst_t is not None:
            FBConnect(src_lcl_t, dst_t)
            connected += 1

        src_lcl_r = find_anim_node(rot_out, "Lcl Rotation")
        dst_r = find_anim_node(rcv_in, "Rotation")
        if src_lcl_r is not None and dst_r is not None:
            FBConnect(src_lcl_r, dst_r)
            connected += 1

    return relation, len(skeleton_pairs), connected


new_root, pairs = duplicate_children_under_new_root(TARGET_NAME, NEW_ROOT_NAME)
print("Created new top-level node: '{0}'".format(new_root.LongName))
print("Total pairs cloned: {0}".format(len(pairs)))

relation, skel_count, connection_count = build_relation_local(RELATION_NAME, pairs)
print("Relation '{0}': {1} skeleton pair(s), {2} channel connection(s).".format(
    relation.LongName, skel_count, connection_count))
