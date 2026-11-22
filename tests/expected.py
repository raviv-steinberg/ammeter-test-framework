"""
Expected values taken from README.md, shared by several test files.
The tests compare the code against these values, so README.md acts as the specification.
"""

# Command each ammeter answers to.
COMMANDS = {
    'greenlee': 'MEASURE_GREENLEE -get_measurement',
    'entes': 'MEASURE_ENTES -get_data',
    'circutor': 'MEASURE_CIRCUTOR -get_measurement',
}

# Lowest and highest current each ammeter can return, worked out from the input ranges in README.md.
CURRENT_RANGES = {
    # I = V / R, V in 1-10 V, R in 0.1-100 ohm: 1 / 100 up to 10 / 0.1.
    'greenlee': (0.01, 100.0),

    # I = B * K, B in 0.01-0.1 T, K in 500-2000: 0.01 * 500 up to 0.1 * 2000.
    'entes': (5.0, 200.0),

    # I = sum(V * dt), 10 samples, V in 0.1-1.0 V, dt in 0.001-0.01 s: 10 * 0.1 * 0.001 up to 10 * 1.0 * 0.01.
    'circutor': (0.001, 0.1),
}
