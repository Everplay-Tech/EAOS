import numpy as np

class WiseGrandfatherNN:
    def __init__(self):
        self.weights1 = np.array([[0.01, 0.11, 0.21, 0.31], [0.41, 0.51, 0.61, 0.71], [0.81, 0.91, 1.01, 1.11]])
        self.bias1 = np.array([0.01, 0.11, 0.21])
        self.weights2 = np.array([[0.31, 0.41, 0.51]])
        self.bias2 = np.array([0.01])
        self.learning_rate = 0.01
        self.history = []

    def relu(self, x):
        return np.maximum(0, x)

    def predict(self, features):
        hidden = self.relu(np.dot(features, self.weights1.T) + self.bias1)
        output = np.dot(hidden, self.weights2.T) + self.bias2
        return output[0]

    def update(self, actual, predicted, features):
        error = actual - predicted
        hidden = self.relu(np.dot(features, self.weights1.T) + self.bias1)
        grad2 = error * hidden
        self.weights2 -= self.learning_rate * grad2
        self.bias2 -= self.learning_rate * error
        grad1 = error * (self.weights2.T * (hidden > 0))
        self.weights1 -= self.learning_rate * np.outer(grad1[0], features)
        self.bias1 -= self.learning_rate * np.sum(grad1, axis=1)
        self.history.append(actual)
        if len(self.history) > 10:
            self.history.pop(0)

if __name__ == "__main__":
    model = WiseGrandfatherNN()
    features = np.array([0.1, 0.2, 0.3, 0.4])
    pred = model.predict(features)
    print(f"Initial Prediction: {pred}")
    model.update(3.5, pred, features)
    new_pred = model.predict(features)
    print(f"Prediction after update: {new_pred}")
