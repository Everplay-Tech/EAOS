import numpy as np

class TurgonNN:
    def __init__(self):
        self.weights1 = np.array([[6.1, 6.2, 6.3, 6.4], [6.5, 6.6, 6.7, 6.8], [6.9, 7.0, 7.1, 7.2]])
        self.bias1 = np.array([6.1, 6.2, 6.3])
        self.weights2 = np.array([[6.4, 6.5, 6.6]])
        self.bias2 = np.array([6.1])
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
    model = TurgonNN()
    features = np.array([6.1, 6.2, 6.3, 6.4])
    pred = model.predict(features)
    print(f"Initial Prediction: {pred}")
    model.update(7.0, pred, features)
    new_pred = model.predict(features)
    print(f"Prediction after update: {new_pred}")
