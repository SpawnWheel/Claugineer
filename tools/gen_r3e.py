"""Generate ctypes structs from the official r3e.h (sector3studios/r3e-api)."""
import re
import sys

src = open(sys.argv[1], encoding="utf-8").read()
src = re.sub(r"//.*", "", src)
src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)

consts = {}
for m in re.finditer(r"\b(R3E_[A-Z0-9_]+)\s*=\s*(-?\d+)", src):
    consts[m.group(1)] = int(m.group(2))
for m in re.finditer(r'#define\s+(R3E_\w+)\s+"([^"]+)"', src):
    consts[m.group(1)] = m.group(2)

enums = set(re.findall(r"\}\s*(r3e_\w+)\s*;", src))
base = {"r3e_int32": "ctypes.c_int32", "r3e_float32": "ctypes.c_float",
        "r3e_float64": "ctypes.c_double", "r3e_u8char": "ctypes.c_uint8"}

structs = []
for m in re.finditer(r"typedef\s+struct\s*\{(.*?)\}\s*(r3e_\w+)\s*;", src, re.S):
    body, name = m.group(1), m.group(2)
    fields = []
    for fm in re.finditer(r"(r3e_\w+)\s+(\w+)\s*((?:\[\s*\w+\s*\])*)\s*;", body):
        typ, fname, dims = fm.groups()
        if typ in base:
            ct = base[typ]
        elif any(s == typ for s, _ in structs):
            ct = typ
        else:                       # enum -> int32
            ct = "ctypes.c_int32"
        for d in reversed(re.findall(r"\[\s*(\w+)\s*\]", dims)):
            n = int(d) if d.isdigit() else consts[d]
            ct = "(%s * %d)" % (ct, n)
        fields.append((fname, ct))
    structs.append((name, fields))

out = []
for name, fields in structs:
    out.append("class %s(ctypes.Structure):" % name)
    out.append("    _pack_ = 1")
    out.append("    _fields_ = [")
    for f, ct in fields:
        out.append('        ("%s", %s),' % (f, ct))
    out.append("    ]\n\n")
print("# --- generated from r3e.h v%d.%d by gen_r3e.py - do not edit by hand ---" % (
    consts["R3E_VERSION_MAJOR"], consts["R3E_VERSION_MINOR"]))
print("R3E_VERSION_MAJOR = %d" % consts["R3E_VERSION_MAJOR"])
print("R3E_VERSION_MINOR = %d" % consts["R3E_VERSION_MINOR"])
print("MAP_NAME = %r\n\n" % consts["R3E_SHARED_MEMORY_NAME"])
print("\n".join(out).rstrip() + "\n")
print("# --- end generated ---", file=sys.stderr)
