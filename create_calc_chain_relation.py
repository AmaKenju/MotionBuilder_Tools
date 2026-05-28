# -*- coding: utf-8 -*-
# Builds a Relation Constraint with two parallel calculation chains:
#
#   Vector to Number ─► Add (a+b) ─► Divide (a/b) ─► Multiply (axb) ─► Subtract (a-b)
#                       b=140         b=125          b=100             b=100
#
# The b inputs are set as default (unconnected) values on the op boxes themselves,
# matching the small "140.00" / "125.00" / ... visualizations in the editor.
# No sender / receiver model boxes are created — only the intermediate math.
# Python 2.7 / Python 3.7+ compatible.

from pyfbsdk import FBConstraintRelation, FBConnect


RELATION_NAME = "CalcChain_Relation"

P_VEC_TO_NUM = ("Converters", "Vector to Number")
P_ADD = ("Number", "Add (a + b)")
P_DIV = ("Number", "Divide (a/b)")
P_MUL = ("Number", "Multiply (a x b)")
P_SUB = ("Number", "Subtract (a - b)")

# default value applied to the unconnected 'b' input of each op
B_CONSTANTS = {
    "add": 140.0,
    "div": 125.0,
    "mul": 100.0,
    "sub": 100.0,
}


def try_create(relation, group, name):
    try:
        return relation.CreateFunctionBox(group, name)
    except Exception:
        return None


def find_anim_node(parent, *names):
    if parent is None:
        return None
    for n in parent.Nodes:
        for target in names:
            if n.Name == target:
                return n
    return None


def dump_box(label, box):
    print("--- {0} ({1}) ---".format(label, type(box).__name__))
    if box is None:
        return
    out = box.AnimationNodeOutGet()
    if out:
        print("  OUT animation nodes:")
        for n in out.Nodes:
            print("    - {0}".format(n.Name))
    inp = box.AnimationNodeInGet()
    if inp:
        print("  IN animation nodes:")
        for n in inp.Nodes:
            print("    - {0}".format(n.Name))
    print("  Properties:")
    for p in box.PropertyList:
        print("    - {0}".format(p.Name))


def set_default_value(box, in_node, prop_names, value):
    """Try (1) the box property, (2) WriteData on the animation node."""
    for pn in prop_names:
        prop = box.PropertyList.Find(pn)
        if prop is not None:
            try:
                prop.Data = value
                return "property '{0}'".format(pn)
            except Exception:
                pass
    if in_node is not None:
        try:
            in_node.WriteData([float(value)])
            return "WriteData"
        except Exception as e:
            print("    WriteData failed: {0}".format(e))
    return None


def build_chain(relation, y_offset, diag=False):
    vec_box = try_create(relation, *P_VEC_TO_NUM)
    add_box = try_create(relation, *P_ADD)
    div_box = try_create(relation, *P_DIV)
    mul_box = try_create(relation, *P_MUL)
    sub_box = try_create(relation, *P_SUB)

    ops = {
        "Vector to Number": vec_box,
        "Add": add_box,
        "Divide": div_box,
        "Multiply": mul_box,
        "Subtract": sub_box,
    }
    for n, b in ops.items():
        if b is None:
            print("ERROR: could not create '{0}' box.".format(n))
            return None

    if diag:
        dump_box("Vector to Number", vec_box)
        dump_box("Add (a + b)", add_box)

    op_x = (0, 350, 700, 1050, 1400)
    relation.SetBoxPosition(vec_box, op_x[0], y_offset)
    relation.SetBoxPosition(add_box, op_x[1], y_offset)
    relation.SetBoxPosition(div_box, op_x[2], y_offset)
    relation.SetBoxPosition(mul_box, op_x[3], y_offset)
    relation.SetBoxPosition(sub_box, op_x[4], y_offset)

    def out_node(box, *names):
        return find_anim_node(box.AnimationNodeOutGet(), *names)

    def in_node(box, *names):
        return find_anim_node(box.AnimationNodeInGet(), *names)

    def connect(src, dst, label_):
        if src is not None and dst is not None:
            FBConnect(src, dst)
        else:
            print("  WARN: missing pin '{0}' (src={1}, dst={2})".format(
                label_, src, dst))

    vec_x = out_node(vec_box, "X", "x", "Result.X")
    add_a = in_node(add_box, "a", "A")
    div_a = in_node(div_box, "a", "A")
    mul_a = in_node(mul_box, "a", "A")
    sub_a = in_node(sub_box, "a", "A")

    connect(vec_x, add_a, "vec.X -> add.a")
    connect(out_node(add_box, "Result", "Output", "Out"), div_a, "add -> div.a")
    connect(out_node(div_box, "Result", "Output", "Out"), mul_a, "div -> mul.a")
    connect(out_node(mul_box, "Result", "Output", "Out"), sub_a, "mul -> sub.a")

    for short_label, op_box, val in (
        ("add", add_box, B_CONSTANTS["add"]),
        ("div", div_box, B_CONSTANTS["div"]),
        ("mul", mul_box, B_CONSTANTS["mul"]),
        ("sub", sub_box, B_CONSTANTS["sub"]),
    ):
        b_in = in_node(op_box, "b", "B")
        result = set_default_value(op_box, b_in, ("b", "B"), val)
        if result is None:
            print("  WARN: could not set '{0}.b' default to {1}".format(short_label, val))
        elif diag:
            print("  set {0}.b={1} via {2}".format(short_label, val, result))

    return {
        "vec_to_num": vec_box,
        "add": add_box, "div": div_box, "mul": mul_box, "sub": sub_box,
    }


relation = FBConstraintRelation(RELATION_NAME)
relation.Active = True

chain1 = build_chain(relation, 0, diag=True)
chain2 = build_chain(relation, 400, diag=False)

if chain1 and chain2:
    print("\nOK: '{0}' created with 2 calculation chains.".format(relation.LongName))
else:
    print("\nFAILED to build both chains.")
