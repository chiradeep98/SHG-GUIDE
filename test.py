# test_translate_isolated.py
from deep_translator import MyMemoryTranslator

result = MyMemoryTranslator(source="hi-IN", target="en-US").translate("नमस्ते")
print(result)