from gtts import gTTS

text = "नमस्ते, आपका दिन शुभ हो। यह एक परीक्षण संदेश है।"
tts = gTTS(text=text, lang="hi")
tts.save("output.mp3")
print("Saved output.mp3 — open it to listen.")