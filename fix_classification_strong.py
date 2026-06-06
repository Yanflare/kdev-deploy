import pathlib

TARGET = pathlib.Path('/home/yanflare/build2/orchestrator/kdev_orchestrator_utils.py')
content = TARGET.read_text(encoding='utf-8')

new_classify = '''
def classify_message(message):
    """STRICT classification — keep simple factual questions on the 9B"""
    msg = message.strip().lower()
    
    if msg.startswith("discussion mode"):
        return "DISCUSSION"
    
    # Simple factual / short questions → keep on 9B
    if len(msg.split()) <= 15 and any(k in msg for k in [
        "what is", "what's", "who is", "when is", "where is", "how many",
        "current time", "current date", "hostname", "uptime", "weather",
        "capital of", "population of", "how old", "how tall", "how big"
    ]):
        return "DISCUSSION"
    
    # Discussion triggers
    triggers = [
        "hypothetically", "theoretically", "how would you", "thought process",
        "what would you", "discuss", "how do you", "what do you think",
        "how do you feel", "evaluate this", "reflect", "tell me about yourself",
        "your opinion", "your thoughts", "do you think", "what is your"
    ]
    if any(t in msg for t in triggers):
        return "DISCUSSION"
    
    return "TASK"
'''

# Replace the entire function
start = content.find("def classify_message(message):")
end = content.find("def ", start + 1)
if start != -1 and end != -1:
    content = content[:start] + new_classify + content[end:]

TARGET.write_text(content, encoding='utf-8')
print("✅ Strong classification patch applied")
