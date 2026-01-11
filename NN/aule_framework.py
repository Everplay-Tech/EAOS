import numpy as np

class AuleFramework:
    def __init__(self, num_inputs=4, hidden_size=3, num_outputs=1, activation='relu'):
        self.num_inputs = num_inputs
        self.hidden_size = hidden_size
        self.num_outputs = num_outputs
        self.activation = activation
        self.learning_rate = 0.01
        self.history = []

    def forge_nn(self):
        weights1 = np.random.rand(self.hidden_size, self.num_inputs) * 0.1
        bias1 = np.random.rand(self.hidden_size) * 0.1
        weights2 = np.random.rand(self.num_outputs, self.hidden_size) * 0.1
        bias2 = np.random.rand(self.num_outputs) * 0.1
        return {'weights1': weights1, 'bias1': bias1, 'weights2': weights2, 'bias2': bias2}

    def activate(self, x):
        if self.activation == 'relu':
            return np.maximum(0, x)
        elif self.activation == 'sigmoid':
            return 1 / (1 + np.exp(-x))
        elif self.activation == 'tanh':
            return np.tanh(x)
        return x

    def predict(self, nn, features):
        hidden = self.activate(np.dot(features, nn['weights1'].T) + nn['bias1'])
        output = np.dot(hidden, nn['weights2'].T) + nn['bias2']
        return output[0]

    def update(self, nn, actual, predicted, features):
        error = actual - predicted
        hidden = self.activate(np.dot(features, nn['weights1'].T) + nn['bias1'])
        if self.activation == 'relu':
            deriv = (hidden > 0).astype(float)
        elif self.activation == 'sigmoid':
            deriv = hidden * (1 - hidden)
        elif self.activation == 'tanh':
            deriv = 1 - hidden**2
        else:
            deriv = np.ones_like(hidden)
        grad2 = error * hidden
        nn['weights2'] -= self.learning_rate * np.outer(grad2, hidden).T
        nn['bias2'] -= self.learning_rate * error
        grad1 = grad2[:, np.newaxis] * nn['weights2'].T * deriv
        nn['weights1'] -= self.learning_rate * np.dot(grad1.T, features[np.newaxis, :])
        nn['bias1'] -= self.learning_rate * np.sum(grad1, axis=0)
        self.history.append(actual)
        if len(self.history) > 10:
            self.history.pop(0)
        return nn

if __name__ == "__main__":
    framework = AuleFramework()
    nn = framework.forge_nn()
    features = np.array([0.1, 0.2, 0.3, 0.4])
    pred = framework.predict(nn, features)
    print(f"Initial Prediction: {pred}")
    nn = framework.update(nn, 2.5, pred, features)
    new_pred = framework.predict(nn, features)
    print(f"Prediction after update: {new_pred}")
