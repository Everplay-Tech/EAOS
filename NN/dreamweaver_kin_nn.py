import numpy as np

class DreamweaverKinNN:
    def __init__(self):
        self.weights1 = np.array([[0.55, 0.65, 0.75, 0.85], [0.95, 1.05, 1.15, 1.25], [1.35, 1.45, 1.55, 1.65]])
        self.bias1 = np.array([0.55, 0.65, 0.75])
        self.weights2 = np.array([[0.85, 0.95, 1.05]])
        self.bias2 = np.array([0.55])
        self.learning_rate = 0.01
        self.history = []

    def relu(self, x):
        return np.maximum(0, x)

    def predict(self, features):
        hidden = self.relu(np.dot(features, self.weights1.T) + self.bias1)
        output = np.dot(hidden, self.weights2.T) + self.bias2 + np.random.uniform(-0.1, 0.1)
        return output[0]

    def update(self, actual, predicted, features):
        error = actual - predicted
        hidden = self.relu(np.dot(features, self.weights1.T) + self.bias1)
        grad2 = error * hidden + np.random.uniform(-0.05, 0.05)
        self.weights2 -= self.learning_rate * grad2
        self.bias2 -= self.learning_rate * error
        grad1 = error * (self.weights2.T * (hidden > 0))
        self.weights1 -= self.learning_rate * np.outer(grad1[0], features)
        self.bias1 -= self.learning_rate * np.sum(grad1, axis=1)
        self.history.append(actual)
        if len(self.history) > 10:
            self.history.pop(0)

if __name__ == "__main__":
    model = DreamweaverKinNN()
    features = np.array([5.1, 5.2, 5.3, 5.4])
    pred = model.predict(features)
    print(f"Initial Prediction: {pred}")
    model.update(8.5, pred, features)
    new_pred = model.predict(features)
    print(f"Prediction after update: {new_pred}")
