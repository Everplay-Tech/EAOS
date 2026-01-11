import numpy as np
import json

def save_model(nn, filename='model.json'):
    state = {
        'weights1': nn.weights1.tolist() if hasattr(nn, 'weights1') else None,
        'bias1': nn.bias1.tolist() if hasattr(nn, 'bias1') else None,
        'weights2': nn.weights2.tolist() if hasattr(nn, 'weights2') else None,
        'bias2': nn.bias2.tolist() if hasattr(nn, 'bias2') else None,
        'history': nn.history
    }
    with open(filename, 'w') as f:
        json.dump(state, f)

def load_model(filename='model.json'):
    with open(filename, 'r') as f:
        state = json.load(f)
    nn = NumpyMandosNN()
    if state['weights1']:
        nn.weights1 = np.array(state['weights1'])
    if state['bias1']:
        nn.bias1 = np.array(state['bias1'])
    if state['weights2']:
        nn.weights2 = np.array(state['weights2'])
    if state['bias2']:
        nn.bias2 = np.array(state['bias2'])
    nn.history = state['history']
    return nn

if __name__ == "__main__":
    from .core import generate_nn
    nn = generate_nn()
    save_model(nn)
    loaded_nn = load_model()
    print("Model saved and loaded successfully.")
