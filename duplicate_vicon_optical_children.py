from pyfbsdk import FBFindModelByLabelName, FBModelNull, FBSystem


TARGET_NAME = "Vicon:Optical"
NEW_ROOT_NAME = "Vicon:Optical_copy"


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


def clone_hierarchy(model, new_parent, target_namespace):
    clone = model.Clone()
    if clone is None:
        return None
    clone.Parent = new_parent

    _, short = split_namespace(model.LongName)
    clone.LongName = "{0}:{1}".format(target_namespace, short)

    for child in list(model.Children):
        clone_hierarchy(child, clone, target_namespace)
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

    duplicates = []
    for child in list(parent.Children):
        base_ns, _ = split_namespace(child.LongName)
        if not base_ns:
            base_ns = child.Name
        new_ns = make_unique("{0}_copy".format(base_ns), existing_namespaces)
        result = clone_hierarchy(child, new_root, new_ns)
        if result is not None:
            duplicates.append((new_ns, result))

    FBSystem().Scene.Evaluate()
    return new_root, duplicates


new_root, created = duplicate_children_under_new_root(TARGET_NAME, NEW_ROOT_NAME)
print("Created new top-level node: '{0}'".format(new_root.LongName))
print("Subtrees duplicated under it: {0}".format(len(created)))
for ns, root in created:
    print(" - namespace='{0}', root='{1}'".format(ns, root.LongName))
