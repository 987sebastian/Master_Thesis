import math

def clamp(value, low, high):
    return max(low, min(high, value))


def clamp01(value):
    return clamp(value, 0.0, 1.0)


def mix(a, b, t):
    return a * (1.0 - t) + b * t


def hash32(value):
    value &= 0xFFFFFFFF
    value ^= value >> 16
    value = (value * 0x7FEB352D) & 0xFFFFFFFF
    value ^= value >> 15
    value = (value * 0x846CA68B) & 0xFFFFFFFF
    value ^= value >> 16
    return value & 0xFFFFFFFF


def noise2(x, y, seed=0):
    xi = int(math.floor(x * 4096.0))
    yi = int(math.floor(y * 4096.0))
    si = int(seed)
    mixed = hash32(xi * 0x1F123BB5 ^ yi * 0x05491333 ^ si * 0x9E3779B9)
    return mixed / 0xFFFFFFFF


def fbm(x, y, seed=0):
    total = 0.0
    amplitude = 0.5
    frequency = 1.0
    for octave in range(4):
        total += amplitude * noise2(x * frequency, y * frequency, seed + octave * 19)
        frequency *= 2.03
        amplitude *= 0.5
    return total
