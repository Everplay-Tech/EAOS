import numpy as np

class UngoliantNN:
    def __init__(self):
        self.weights1 = np.random.rand(5, 4) * 0.3 - 0.15
        self.bias1 = np.random.rand(5) * 0.3 - 0.15
        self.weights2 = np.random.rand(1, 5) * 0.3 - 0.15
        self.bias2 = np.random.rand(1) * 0.3 - 0.15
        self.learning_rate = 0.02
        self.history = []

    def sigmoid(self, x):
        return 1 / (1 + np.exp(-x))

    def predict(self, features):
        hidden = self.sigmoid(np.dot(self.weights1, features) + self.bias1)
        output = np.dot(self.weights2, hidden) + self.bias2
        return output[0]

    def update(self, actual, predicted, features):
        error = actual - predicted
        hidden = self.sigmoid(np.dot(self.weights1, features) + self.bias1)
        grad2 = error * hidden
        self.weights2 -= self.learning_rate * np.outer(grad2, [1]).T
        self.bias2 -= self.learning_rate * error
        grad1 = np.dot(self.weights2.T, error) * hidden * (1 - hidden)
        self.weights1 -= self.learning_rate * np.outer(grad1, features)
        self.bias1 -= self.learning_rate * grad1
        self.history.append(actual)
        if len(self.history) > 10:
            self.history.pop(0)

if __name__ == "__main__":
    model = UngoliantNN()
    features = np.array([4.0, 5.0, 6.0, 7.0])
    pred = model.predict(features)
    print(f"Initial Threat Level: {pred}")
    model.update(8.0, pred, features)
    new_pred = model.predict(features)
    print(f"Constricted Threat Level: {new_pred}")
