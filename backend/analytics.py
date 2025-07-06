# backend/analytics.py
import csv
import os
from collections import Counter

data_file = os.path.join(os.getcwd(), 'backend', 'prediction_logs.csv')

# Ensure the file exists with headers
def init_csv():
    if not os.path.exists(data_file):
        with open(data_file, mode='w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['filename', 'prediction', 'confidence'])

# Log a prediction
def log_prediction(filename, prediction, confidence):
    init_csv()
    with open(data_file, mode='a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([filename, prediction, confidence])

# Basic summary

def get_summary():
    init_csv()
    predictions = []
    confidences = []
    with open(data_file, mode='r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            predictions.append(row['prediction'])
            confidences.append(float(row['confidence']))

    count = Counter(predictions)
    avg_conf = sum(confidences) / len(confidences) if confidences else 0

    return {
        'total': len(predictions),
        'counts': dict(count),
        'average_confidence': round(avg_conf, 2)
    }
