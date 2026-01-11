import numpy as np

class MaedhrosNN:
    def __init__(self):
        self.weights1 = np.array([[4.1, 4.2, 4.3, 4.4], [4.5, 4.6, 4.7, 4.8], [4.9, 5.0, 5.1, 5.2]])
        self.bias1 = np.array([4.1, 4.2, 4.3])
        self.weights2 = np.array([[4.4, 4.5, 4.6]])
        self.bias2 = np.array([4.1])
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
    model = MaedhrosNN()
    features = np.array([4.1, 4.2, 4.3, 4.4])
    pred = model.predict(features)
    print(f"Initial Prediction: {pred}")
    model.update(5.0, pred, features)
    new_pred = model.predict(features)
    print(f"Prediction after update: {new_pred}")
