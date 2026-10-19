"""Symmetrical components: phase (a, b, c) <-> sequence (0, 1, 2).

a = 1∠120°,  [Va; Vb; Vc] = A [V0; V1; V2],  A = [[1, 1, 1], [1, a², a],
[1, a, a²]],  [V0; V1; V2] = (1/3) [[1, 1, 1], [1, a, a²], [1, a², a]] [Va; Vb; Vc].
"""
import numpy as np

a = np.exp(2j * np.pi / 3)
A = np.array([[1, 1, 1], [1, a**2, a], [1, a, a**2]])
A_INV = np.array([[1, 1, 1], [1, a, a**2], [1, a**2, a]]) / 3


def polar(mag, deg):
    return mag * np.exp(1j * np.radians(deg))


def to_sequence(abc):
    """[Va, Vb, Vc] -> [V0, V1, V2]."""
    return A_INV @ np.asarray(abc, complex)


def to_phase(s012):
    """[V0, V1, V2] -> [Va, Vb, Vc]."""
    return A @ np.asarray(s012, complex)
