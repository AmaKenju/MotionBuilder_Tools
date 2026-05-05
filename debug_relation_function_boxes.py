from pyfbsdk import FBConstraintRelation, FBSystem, FBModelSkeleton


skel = None
for c in FBSystem().Scene.Components:
    if isinstance(c, FBModelSkeleton):
        skel = c
        break

if skel is None:
    print("No FBModelSkeleton found in scene.")
else:
    print("Using skeleton: {0}".format(skel.LongName))

    relation = FBConstraintRelation("PROBE_LocalTransform_v2")

    receiver = relation.ConstrainObject(skel)

    print("\n=== Receiver box dir() entries containing 'local'/'lcl'/'transform' ===")
    keywords = ("local", "lcl", "transform")
    for attr in dir(receiver):
        low = attr.lower()
        if any(k in low for k in keywords):
            try:
                val = getattr(receiver, attr)
                print("  - {0}  =  {1!r}".format(attr, val))
            except Exception as e:
                print("  - {0}  (getattr error: {1})".format(attr, e))

    print("\n=== Receiver box ALL public attrs (no underscore) ===")
    for attr in sorted(dir(receiver)):
        if not attr.startswith("_"):
            print("  - {0}".format(attr))
