from google import genai

client = genai.Client(api_key="AIzaSyAQJsHQhZ7dAV7qyub82HaRcIpBlg4GeJI")
response = client.models.generate_content(
    model="gemini-2.0-flash", 
    contents="Explain AI like I'm five."
)

print(response.text)