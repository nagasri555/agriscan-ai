import random

def predict_disease(image_path):
    # Fake predictions (simulate AI)
    classes = ['Healthy', 'Leaf Blight', 'Rust', 'Bacterial Spot']
    prediction = random.choice(classes)
    confidence = round(random.uniform(0.7, 1.0), 2)

    return {
        'prediction': prediction,
        'confidence': confidence
    }
