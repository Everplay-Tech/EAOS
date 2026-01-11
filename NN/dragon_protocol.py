import numpy as np

class DragonNN:
    def __init__(self):
        self.weights1 = np.random.rand(3, 4) * 0.4 - 0.2
        self.bias1 = np.random.rand(3) * 0.4 - 0.2
        self.weights2 = np.random.rand(1, 3) * 0.4 - 0.2
        self.bias2 = np.random.rand(1) * 0.4 - 0.2
        self.learning_rate = 0.025
        self.history = []

    def leaky_relu(self, x):
        return np.where(x > 0, x, 0.01 * x)

    def predict(self, features):
        hidden = self.leaky_relu(np.dot(self.weights1, features) + self.bias1)
        output = np.dot(self.weights2, hidden) + self.bias2
        return output[0]

    def update(self, actual, predicted, features):
        error = actual - predicted
        hidden = self.leaky_relu(np.dot(self.weights1, features) + self.bias1)
        grad2 = error * hidden
        self.weights2 -= self.learning_rate * np.outer(grad2, [1]).T
        self.bias2 -= self.learning_rate * error
        grad1 = np.dot(self.weights2.T, error) * np.where(hidden > 0, 1, 0.01)
        self.weights1 -= self.learning_rate * np.outer(grad1, features)
        self.bias1 -= self.learning_rate * grad1
        self.history.append(actual)
        if len(self.history) > 10:
            self.history.pop(0)

if __name__ == "__main__":
    model = DragonNN()
    features = np.array([1.5, 2.5, 3.5, 4.5])
    pred = model.predict(features)
    print(f"Initial Threat Level: {pred}")
    model.update(5.5, pred, features)
    new_pred = model.predict(features)
    print(f"Constricted Threat Level: {new_pred}")
