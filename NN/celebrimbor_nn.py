import numpy as np

class CelebrimborNN:
    def __init__(self):
        self.weights1 = np.array([[8.1, 8.2, 8.3, 8.4], [8.5, 8.6, 8.7, 8.8], [8.9, 9.0, 9.1, 9.2]])
        self.bias1 = np.array([8.1, 8.2, 8.3])
        self.weights2 = np.array([[8.4, 8.5, 8.6]])
        self.bias2 = np.array([8.1])
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
    model = CelebrimborNN()
    features = np.array([8.1, 8.2, 8.3, 8.4])
    pred = model.predict(features)
    print(f"Initial Prediction: {pred}")
    model.update(9.0, pred, features)
    new_pred = model.predict(features)
    print(f"Prediction after update: {new_pred}")
