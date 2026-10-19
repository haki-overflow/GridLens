"""Transmission line ABCD parameters, voltage regulation and efficiency.

Per-phase models from per-km series impedance z = R + jX (Ω/km) and shunt
admittance y = jB (S/km) over a length l:
  short       A = D = 1, B = Z, C = 0
  medium (π)  A = D = 1 + ZY/2, B = Z, C = Y (1 + ZY/4)
  long        γ = √(zy), Zc = √(z/y), A = D = cosh γl, B = Zc sinh γl,
              C = sinh γl / Zc
V_S = A V_R + B I_R, I_S = C V_R + D I_R (per phase, kV and kA).
Regulation % = (|V_S|/|A| − |V_R|) / |V_R| · 100, efficiency = P_R / P_S.
"""
import numpy as np

MODELS = ("short", "medium (π)", "long")


def abcd(model, R, X, B_uS, length):
    """ABCD constants (B in Ω, C in S) for one of MODELS."""
    z, y = complex(R, X), complex(0, B_uS * 1e-6)
    Z, Y = z * length, y * length
    if model == "short":
        return 1 + 0j, Z, 0j, 1 + 0j
    if model == "medium (π)":
        A = 1 + Z * Y / 2
        return A, Z, Y * (1 + Z * Y / 4), A
    if model == "long":
        g, zc = np.sqrt(z * y), np.sqrt(z / y)
        A = np.cosh(g * length)
        return A, zc * np.sinh(g * length), np.sinh(g * length) / zc, A
    raise ValueError(f"model must be one of {MODELS}")


def performance(model, R, X, B_uS, length, VR_kV, PR_MW, pf, lagging=True):
    """Sending-end quantities for a 3-phase load at the receiving end
    (VR_kV line-to-line, PR_MW three-phase, power factor pf)."""
    A, B, C, D = abcd(model, R, X, B_uS, length)
    VR = VR_kV / np.sqrt(3) + 0j                                   # kV per phase
    phi = np.arccos(pf) * (-1 if lagging else 1)
    IR = PR_MW / (np.sqrt(3) * VR_kV * pf) * np.exp(1j * phi)      # kA
    VS = A * VR + B * IR
    IS = C * VR + D * IR
    SS, SR = 3 * VS * np.conj(IS), 3 * VR * np.conj(IR)            # MVA
    out = dict(A=A, B=B, C=C, D=D, VR=VR, IR=IR, VS=VS, IS=IS, SS=SS, SR=SR,
               VS_LL=abs(VS) * np.sqrt(3),
               reg=(abs(VS) / abs(A) - abs(VR)) / abs(VR) * 100,
               eff=SR.real / SS.real * 100, loss=SS.real - SR.real,
               check=A * D - B * C)
    if model == "long":
        z, y = complex(R, X), complex(0, B_uS * 1e-6)
        out.update(gamma=np.sqrt(z * y), Zc=np.sqrt(z / y),
                   SIL=VR_kV ** 2 / abs(np.sqrt(z / y)))
    return out
