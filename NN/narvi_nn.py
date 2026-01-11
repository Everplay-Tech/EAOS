import numpy as np

class NarviNN:
    def __init__(self):
        self.weights1 = np.array([[7.0 * np.sqrt(2), 7.1 * np.sqrt(2)], [7.2 * np.sqrt(2), 7.3 * np.sqrt(2)], [7.4 * np.sqrt(2), 7.5 * np.sqrt(2)], [7.6 * np.sqrt(2), 7.7 * np.sqrt(2)], [7.8 * np.sqrt(2), 7.9 * np.sqrt(2)]])
        self.bias1 = np.array([7.0 * np.sqrt(2), 7.1 * np.sqrt(2), 7.2 * np.sqrt(2), 7.3 * np.sqrt(2), 7.4 * np.sqrt(2)])
        self.weights2 = np.array([[7.3 * np.sqrt(2), 7.4 * np.sqrt(2), 7.5 * np.sqrt(2), 7.6 * np.sqrt(2), 7.7 * np.sqrt(2)]])
        self.bias2 = np.array([7.0 * np.sqrt(2)])
        self.learning_rate = 0.01
        self.history = []

    def tanh(self, x):
        return np.tanh(x)

    def predict(self, features):
        hidden = self.tanh(np.dot(features, self.weights1.T) + self.bias1)
        output = np.dot(hidden, self.weights2.T) + self.bias2
        return output[0]

    def update(self, actual, predicted, features):
        error = actual - predicted
        hidden = self.tanh(np.dot(features, self.weights1.T) + self.bias1)
        grad2 = error * hidden
        self.weights2 -= self.learning_rate * grad2
        self.bias2 -= self.learning_rate * error
        grad1 = error * (self.weights2.T * (1 - hidden**2))
        self.weights1 -= self.learning_rate * np.outer(grad1[0], features)
        self.bias1 -= self.learning_rate * np.sum(grad1, axis=1)
        self.history.append(actual)
        if len(self.history) > 10:
            self.history.pop(0)

if __name__ == "__main__":
    model = NarviNN()
    features = np.array([7.0, 7.1])
    pred = model.predict(features)
    print(f"Initial Prediction: {pred}")
    model.update(8.5, pred, features)
    new_pred = model.predict(features)
    print(f"Prediction after update: {new_pred}")
