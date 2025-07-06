# model_api.py
import random

def predict_disease(image_bytes):
    # Simulate a prediction
    possible_labels = ['Healthy', 'Leaf Spot', 'Blight', 'Rust']
    prediction = random.choice(possible_labels)
    confidence = round(random.uniform(0.75, 0.99), 2)

    return {
        "prediction": prediction,
        "confidence": confidence
    }
