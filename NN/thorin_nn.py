import numpy as np

class ThorinNN:
    def __init__(self):
        self.weights1 = np.array([[8.0 * np.sqrt(2), 8.1 * np.sqrt(2), 8.2 * np.sqrt(2)], [8.3 * np.sqrt(2), 8.4 * np.sqrt(2), 8.5 * np.sqrt(2)]])
        self.bias1 = np.array([8.0 * np.sqrt(2), 8.1 * np.sqrt(2), 8.2 * np.sqrt(2)])
        self.weights2 = np.array([[8.3 * np.sqrt(2), 8.4 * np.sqrt(2), 8.5 * np.sqrt(2)]])
        self.bias2 = np.array([8.0 * np.sqrt(2)])
        self.learning_rate = 0.01
        self.history = []

    def leaky_relu(self, x):
        return np.maximum(0.01 * x, x)

    def predict(self, features):
        hidden = self.leaky_relu(np.dot(features, self.weights1.T) + self.bias1)
        output = np.dot(hidden, self.weights2.T) + self.bias2
        return output[0]

    def update(self, actual, predicted, features):
        error = actual - predicted
        hidden = self.leaky_relu(np.dot(features, self.weights1.T) + self.bias1)
        grad2 = error * hidden
        self.weights2 -= self.learning_rate * grad2 * (1 + abs(error))
        self.bias2 -= self.learning_rate * error
        grad1 = error * (self.weights2.T * (hidden > 0) + 0.01 * (hidden <= 0))
        self.weights1 -= self.learning_rate * np.outer(grad1[0], features)
        self.bias1 -= self.learning_rate * np.sum(grad1, axis=1)
        self.history.append(actual)
        if len(self.history) > 10:
            self.history.pop(0)

if __name__ == "__main__":
    model = ThorinNN()
    features = np.array([8.0, 8.1, 8.2])
    pred = model.predict(features)
    print(f"Initial Prediction: {pred}")
    model.update(9.5, pred, features)
    new_pred = model.predict(features)
    print(f"Prediction after update: {new_pred}")
