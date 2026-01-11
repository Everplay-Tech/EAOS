# Eä Muscle: Fëanor v6.0
# Neural network weights for the Fëanor family muscle
# Architecture: 4-input → 1-output (ReLU)

import numpy as np

# Weight vector (4)
W = np.array([0.123456, -0.234567, 0.345678, -0.456789])

# Output bias (1)
b = 0.777777

# Neural network forward pass
def forward(inputs):
    output = np.dot(inputs, W) + b
    return np.maximum(0, output)

# Example usage
if __name__ == "__main__":
    test_input = np.array([1.0, -1.0, 0.5, -0.5])
    result = forward(test_input)
    print(f"Fëanor inference: {result}")
