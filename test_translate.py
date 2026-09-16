from deep_translator import GoogleTranslator

# Hindi -> English
hindi_text = "मैं अचार बनाती हूं और उसे अपने पड़ोसियों को बेचती हूं।"
english_result = GoogleTranslator(source="hi", target="en").translate(hindi_text)
print("Hindi -> English:")
print(hindi_text)
print("->", english_result)
print()

# English -> Hindi, using a sentence closer to your actual roadmap output
english_text = (
    "You could get support from the National Handicraft Development "
    "Programme, which offers design support and market linkage."
)
hindi_result = GoogleTranslator(source="en", target="hi").translate(english_text)
print("English -> Hindi:")
print(english_text)
print("->", hindi_result)