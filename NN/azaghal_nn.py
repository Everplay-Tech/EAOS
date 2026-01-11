import numpy as np

class AzaghalNN:
    def __init__(self):
        self.weights1 = np.array([[6.0 * np.sqrt(2), 6.1 * np.sqrt(2), 6.2 * np.sqrt(2), 6.3 * np.sqrt(2), 6.4 * np.sqrt(2)], [6.5 * np.sqrt(2), 6.6 * np.sqrt(2), 6.7 * np.sqrt(2), 6.8 * np.sqrt(2), 6.9 * np.sqrt(2)]])
        self.bias1 = np.array([6.0 * np.sqrt(2), 6.1 * np.sqrt(2)])
        self.weights2 = np.array([[6.3 * np.sqrt(2), 6.4 * np.sqrt(2)]])
        self.bias2 = np.array([6.0 * np.sqrt(2)])
        self.learning_rate = 0.01
        self.history = []

    def sigmoid(self, x):
        return 1 / (1 + np.exp(-x))

    def predict(self, features):
        hidden = self.sigmoid(np.dot(features, self.weights1.T) + self.bias1)
        output = np.dot(hidden, self.weights2.T) + self.bias2
        return output[0]

    def update(self, actual, predicted, features):
        error = actual - predicted
        hidden = self.sigmoid(np.dot(features, self.weights1.T) + self.bias1)
        grad2 = error * hidden
        self.weights2 -= self.learning_rate * grad2 * error**2  # Quadratic for prowess
        self.bias2 -= self.learning_rate * error
        grad1 = error * (self.weights2.T * hidden * (1 - hidden))
        self.weights1 -= self.learning_rate * np.outer(grad1[0], features)
        self.bias1 -= self.learning_rate * np.sum(grad1, axis=1)
        self.history.append(actual)
        if len(self.history) > 10:
            self.history.pop(0)

if __name__ == "__main__":
    model = AzaghalNN()
    features = np.array([6.0, 6.1, 6.2, 6.3, 6.4])
    pred = model.predict(features)
    print(f"Initial Prediction: {pred}")
    model.update(7.5, pred, features)
    new_pred = model.predict(features)
    print(f"Prediction after update: {new_pred}")
