import numpy as np
try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

class BaseMandosNN:
    def __init__(self):
        pass

    def predict(self, features):
        pass

    def update(self, actual, predicted, features):
        pass

class NumpyMandosNN(BaseMandosNN):
    def __init__(self, input_size=4, hidden_size=3, output_size=1):
        self.weights1 = np.random.rand(hidden_size, input_size) * 0.1
        self.bias1 = np.random.rand(hidden_size) * 0.1
        self.weights2 = np.random.rand(output_size, hidden_size) * 0.1
        self.bias2 = np.random.rand(output_size) * 0.1
        self.learning_rate = 0.01
        self.history = []

    def relu(self, x):
        return np.maximum(0, x)

    def predict(self, features):
        hidden = self.relu(np.dot(self.weights1, features) + self.bias1)
        output = np.dot(self.weights2, hidden) + self.bias2
        return output[0]

    def update(self, actual, predicted, features):
        error = actual - predicted
        hidden = self.relu(np.dot(self.weights1, features) + self.bias1)
        grad2 = np.outer(error * hidden, [1])
        self.weights2 -= self.learning_rate * grad2.T
        self.bias2 -= self.learning_rate * error
        grad1 = error * np.dot(self.weights2.T, (hidden > 0))
        self.weights1 -= self.learning_rate * np.outer(grad1, features)
        self.bias1 -= self.learning_rate * grad1
        self.history.append(actual)
        if len(self.history) > 10:
            self.history.pop(0)

class TorchMandosNN(nn.Module):
    def __init__(self, input_size=4, hidden_size=3, output_size=1):
        super().__init__()
        self.fc1 = nn.Linear(input_size, hidden_size)
        self.fc2 = nn.Linear(hidden_size, output_size)
        self.optimizer = optim.Adam(self.parameters(), lr=0.01)
        self.history = []

    def forward(self, features):
        hidden = torch.relu(self.fc1(features))
        output = self.fc2(hidden)
        return output.item()

    def predict(self, features):
        features = torch.tensor(features, dtype=torch.float32)
        with torch.no_grad():
            return self.forward(features)

    def update(self, actual, predicted, features):
        features = torch.tensor(features, dtype=torch.float32)
        target = torch.tensor([actual], dtype=torch.float32)
        output = self.fc2(torch.relu(self.fc1(features)))
        loss = (output - target) ** 2
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()
        self.history.append(actual)
        if len(self.history) > 10:
            self.history.pop(0)

def generate_nn(style='default', use_torch=False, **kwargs):
    if use_torch and TORCH_AVAILABLE:
        return TorchMandosNN(**kwargs)
    else:
        return NumpyMandosNN(**kwargs)

def train_nn(nn, data_samples):
    for sample in data_samples:
        features = np.array(sample[:-1])
        actual = sample[-1]
        pred = nn.predict(features)
        nn.update(actual, pred, features)

if __name__ == "__main__":
    nn = generate_nn()
    features = np.array([1.0, 2.0, 3.0, 4.0])
    pred = nn.predict(features)
    print(f"Initial Prediction: {pred}")
    nn.update(5.0, pred, features)
    new_pred = nn.predict(features)
    print(f"Prediction after update: {new_pred}")
    data_samples = [[1.1, 2.1, 3.1, 4.1, 5.1], [1.2, 2.2, 3.2, 4.2, 5.2]]
    train_nn(nn, data_samples)
    final_pred = nn.predict(np.array([1.3, 2.3, 3.3, 4.3]))
    print(f"Final Prediction after training: {final_pred}")
