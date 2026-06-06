import pathlib

TARGET = pathlib.Path('/home/yanflare/build2/orchestrator/kdev_orchestrator_utils.py')
content = TARGET.read_text(encoding='utf-8')

# Much stricter classification to keep simple factual questions on the 9B
new_classify = '''
def classify_message(message):
    """Return "DISCUSSION" or "TASK" with stricter rules to prevent over-delegation"""
    msg = message.strip().lower()
    if msg.startswith("discussion mode"):
        return "DISCUSSION"
    
    # Simple factual / short questions should stay on 9B
    words = msg.split()
    if len(words) <= 12 and any(word in msg for word in [
        "what is", "what's", "who is", "when is", "where is", "how many",
        "current time", "current date", "hostname", "uptime", "weather",
        "capital of", "population of", "how old"
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

content = content.replace(
    'def classify_message(message):',
    new_classify
)

TARGET.write_text(content, encoding='utf-8')
print("✅ 9B classification tuned — much stricter on simple factual questions")
