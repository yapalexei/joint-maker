"""Minimal STL reader (binary and ASCII), used for the bundled cutout shapes."""

import struct


def read_stl(path):
    """triangles from a binary or ASCII STL file -> list of 3-tuples of (x, y, z)"""
    data = open(path, "rb").read()
    tris = []
    if len(data) >= 84:
        n = struct.unpack_from("<I", data, 80)[0]
        if 84 + 50 * n == len(data):
            for i in range(n):
                v = struct.unpack_from("<12f", data, 84 + 50 * i)
                tris.append((v[3:6], v[6:9], v[9:12]))
            return tris
    cur = []
    for line in data.decode("ascii", "ignore").splitlines():
        t = line.split()
        if t[:1] == ["vertex"]:
            cur.append(tuple(float(x) for x in t[1:4]))
            if len(cur) == 3:
                tris.append(tuple(cur)); cur = []
    return tris
