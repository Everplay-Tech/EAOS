import numpy as np
from .core import generate_nn, train_nn
from .utils import save_model, load_model

nn = generate_nn(input_size=4, hidden_size=3, output_size=1, use_torch=False)
features = np.array([1.0, 2.0, 3.0, 4.0])
pred = nn.predict(features)
print(f"Initial Prediction: {pred}")
nn.update(5.0, pred, features)
new_pred = nn.predict(features)
print(f"Prediction after update: {new_pred}")
data_samples = [[1.1, 2.1, 3.1, 4.1, 5.1], [1.2, 2.2, 3.2, 4.2, 5.2]]
train_nn(nn, data_samples)
final_pred = nn.predict(np.array([1.3, 2.3, 3.3, 4.3]))
print(f"Final Prediction after training: {final_pred}")
save_model(nn, 'test_model.json')
loaded_nn = load_model('test_model.json')
loaded_pred = loaded_nn.predict(np.array([1.3, 2.3, 3.3, 4.3]))
print(f"Loaded Model Prediction: {loaded_pred}")
