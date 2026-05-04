from pyfbsdk import FBFindModelByLabelName


TARGET_NAME = "Vicon:Optical"


def clone_hierarchy(model, new_parent):
    clone = model.Clone()
    clone.Parent = new_parent
    for child in model.Children:
        clone_hierarchy(child, clone)
    return clone


def duplicate_children(parent_name):
    parent = FBFindModelByLabelName(parent_name)
    if parent is None:
        raise RuntimeError("Node not found: {0}".format(parent_name))

    # Snapshot before we start adding clones to the same parent.
    original_children = list(parent.Children)

    duplicates = []
    for child in original_children:
        duplicates.append(clone_hierarchy(child, parent))

    return duplicates


if __name__ == "__main__":
    created = duplicate_children(TARGET_NAME)
    print("Duplicated {0} child node(s) under '{1}'.".format(len(created), TARGET_NAME))
