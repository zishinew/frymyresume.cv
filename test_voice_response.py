import requests

# Use session ID from previous test
session_id = "5f0c521e-bcbb-429a-a6cb-24979913dd9e"

# Create dummy audio file
with open("test_audio.wav", "wb") as f:
    f.write(b'\x00' * 1000)

# Send request
with open("test_audio.wav", "rb") as f:
    files = {"audio": f}
    data = {"session_id": session_id}
    response = requests.post(
        "http://localhost:8000/api/voice-response",
        files=files,
        data=data
    )

print("Status:", response.status_code)
print("Response:", response.json())
