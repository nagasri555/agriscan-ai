import requests
import base64
import os


PLANT_ID_URL = "https://api.plant.id/v2/health_assessment"

def identify_crop_disease(image_path, api_key):
    try:
        with open(image_path, "rb") as image_file:
            image_bytes = base64.b64encode(image_file.read()).decode("utf-8")

        payload = {
            "images": [image_bytes],
            "organs": ["leaf"],
            "modifiers": ["crops_fast", "similar_images"]
        }

        headers = {
            'Content-Type': 'application/json',
            'Api-Key': os.getenv('PLANT_ID_API_KEY')
        }


        response = requests.post(PLANT_ID_URL, json=payload, headers=headers)

        if response.status_code == 200:
            data = response.json()

            if data.get("health_assessment", {}).get("diseases"):
                top = data["health_assessment"]["diseases"][0]
                prediction = top["name"]
                confidence = top["probability"]
            else:
                prediction = "Healthy"
                confidence = 1.0

            suggestions = data.get("suggestions", [])
            plant_name = suggestions[0]["plant"]["name"]["value"] if suggestions else "Unknown Plant"

            return {
                "plant_name": plant_name,
                "prediction": prediction,
                "confidence": confidence,
                "source": "Plant.id"
            }

        elif response.status_code == 429:
            return {"error": "🚫 Too many requests to Plant.id API (HTTP 429). Please wait and try again."}

        else:
            return {"error": f"Plant.id error: {response.status_code}"}

    except Exception as e:
        return {"error": f"Failed to analyze image: {str(e)}"}
