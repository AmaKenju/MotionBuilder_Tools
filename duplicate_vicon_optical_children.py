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


def build_local_relation(name, pairs):
    """Build a Relation Constraint with Lcl IN/OUT pins on both source and destination.

    Both sides use ConstrainObject() to get FBModelPlaceHolder boxes, then
    UseGlobalTransforms=False switches both their input and output animation
    nodes to 'Lcl Translation' / 'Lcl Rotation' / 'Lcl Scaling' (this is the
    Python equivalent of the right-click "Local transformations" menu in the
    Relation editor). The source box's IN pins are simply left unconnected so
    the source model is not actually driven.
    """
    skeleton_pairs = [
        (src, dst) for (src, dst) in pairs
        if isinstance(src, FBModelSkeleton) and isinstance(dst, FBModelSkeleton)
    ]

    relation = FBConstraintRelation(name)
    relation.Active = True

    y_step = 130
    x_source = 0
    x_dest = 700

    connected = 0
    for index, (src_model, dst_model) in enumerate(skeleton_pairs):
        src_box = relation.SetAsSource(src_model)
        dst_box = relation.ConstrainObject(dst_model)

        src_box.UseGlobalTransforms = False
        dst_box.UseGlobalTransforms = False

        y = index * y_step
        relation.SetBoxPosition(src_box, x_source, y)
        relation.SetBoxPosition(dst_box, x_dest, y)

        src_out = src_box.AnimationNodeOutGet()
        dst_in = dst_box.AnimationNodeInGet()

        for ch in ("Lcl Translation", "Lcl Rotation"):
            src_node = find_anim_node(src_out, ch)
            dst_node = find_anim_node(dst_in, ch)
            if src_node is not None and dst_node is not None:
                FBConnect(src_node, dst_node)
                connected += 1

    return relation, len(skeleton_pairs), connected


new_root, pairs = duplicate_children_under_new_root(TARGET_NAME, NEW_ROOT_NAME)
print("Created new top-level node: '{0}'".format(new_root.LongName))
print("Total pairs cloned: {0}".format(len(pairs)))

relation, skel_count, connection_count = build_local_relation(RELATION_NAME, pairs)
print("Relation '{0}': {1} skeleton pair(s), {2} Lcl channel connection(s).".format(
    relation.LongName, skel_count, connection_count))
