import numpy as np

class SpiderNN:
    def __init__(self):
        self.weights1 = np.random.rand(4, 4) * 0.25 - 0.125
        self.bias1 = np.random.rand(4) * 0.25 - 0.125
        self.weights2 = np.random.rand(1, 4) * 0.25 - 0.125
        self.bias2 = np.random.rand(1) * 0.25 - 0.125
        self.learning_rate = 0.02
        self.history = []

    def tanh(self, x):
        return np.tanh(x)

    def predict(self, features):
        hidden = self.tanh(np.dot(self.weights1, features) + self.bias1)
        output = np.dot(self.weights2, hidden) + self.bias2
        return output[0]

    def update(self, actual, predicted, features):
        error = actual - predicted
        hidden = self.tanh(np.dot(self.weights1, features) + self.bias1)
        grad2 = error * hidden
        self.weights2 -= self.learning_rate * np.outer(grad2, [1]).T
        self.bias2 -= self.learning_rate * error
        grad1 = np.dot(self.weights2.T, error) * (1 - hidden**2)
        self.weights1 -= self.learning_rate * np.outer(grad1, features)
        self.bias1 -= self.learning_rate * grad1
        self.history.append(actual)
        if len(self.history) > 10:
            self.history.pop(0)

if __name__ == "__main__":
    model = SpiderNN()
    features = np.array([2.0, 3.0, 4.0, 5.0])
    pred = model.predict(features)
    print(f"Initial Threat Level: {pred}")
    model.update(6.0, pred, features)
    new_pred = model.predict(features)
    print(f"Constricted Threat Level: {new_pred}")
