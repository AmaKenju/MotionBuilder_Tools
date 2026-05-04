from pyfbsdk import FBSystem
scene = FBSystem().Scene

print("=== Scene attributes containing 'Optical' ===")
for attr in dir(scene):
    if 'ptical' in attr:
        print(" -", attr)

print("\n=== Components with 'Optical' or 'Vicon' in name ===")
for c in scene.Components:
    name = getattr(c, 'LongName', '') or ''
    if 'Optical' in name or 'Vicon' in name or 'optical' in name:
        print(" -", type(c).__name__, "|", name)

print("\n=== scene.OpticalDatas (if exists) ===")
if hasattr(scene, 'OpticalDatas'):
    for o in scene.OpticalDatas:
        print(" -", type(o).__name__, "|", o.LongName)
        for ch in getattr(o, 'Children', []):
            print("    *", type(ch).__name__, "|", ch.LongName)
