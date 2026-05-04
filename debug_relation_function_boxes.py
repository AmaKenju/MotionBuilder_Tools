from pyfbsdk import FBConstraintRelation


def dump_box(box, label):
    print("\n=== {0} ===".format(label))
    if box is None:
        print("  (None)")
        return
    print("Type: {0}".format(type(box).__name__))
    print("Properties:")
    for p in box.PropertyList:
        print("  - {0}  (type={1})".format(p.Name, type(p).__name__))
    out = box.AnimationNodeOutGet()
    print("Output animation nodes:")
    if out is not None:
        for n in out.Nodes:
            print("  - {0}".format(n.Name))
    inp = box.AnimationNodeInGet()
    print("Input animation nodes:")
    if inp is not None:
        for n in inp.Nodes:
            print("  - {0}".format(n.Name))


relation = FBConstraintRelation("DEBUG_FunctionBox_Probe")

candidates = [
    ("Senders", "Position"),
    ("Senders", "Rotation"),
    ("Senders", "Source"),
    ("Receivers", "Position"),
    ("Receivers", "Rotation"),
    ("Receivers", "Source"),
]

for group, fname in candidates:
    box = relation.CreateFunctionBox(group, fname)
    dump_box(box, "{0} / {1}".format(group, fname))

print("\n---- DONE ----")
