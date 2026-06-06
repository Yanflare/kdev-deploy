import pathlib

TARGET = pathlib.Path('/home/yanflare/build2/orchestrator/kdev_orchestrator_utils.py')
content = TARGET.read_text(encoding='utf-8')

# Stronger classification prompt to keep simple questions on the 9B
new_classify = '''
def classify_message(message):
    """Return "DISCUSSION" or "TASK" with much stricter rules"""
    msg = message.strip().lower()
    if msg.startswith("discussion mode"):
        return "DISCUSSION"
    
    # Simple factual / short questions should stay on 9B
    if len(msg.split()) <= 8 and any(word in msg for word in [
        "what is", "what's", "who is", "when is", "where is", "how many",
        "current time", "current date", "hostname", "uptime", "weather"
    ]):
        return "DISCUSSION"
    
    # Default triggers for DISCUSSION
    discussion_triggers = [
        "hypothetically", "theoretically", "how would you", "thought process",
        "what would you", "discuss", "how do you", "what do you think",
        "how do you feel", "evaluate this", "reflect", "tell me about yourself",
        "your opinion", "your thoughts", "do you think", "what is your"
    ]
    if any(t in msg for t in discussion_triggers):
        return "DISCUSSION"
    return "TASK"
'''

content = content.replace(
    'def classify_message(message):',
    new_classify
)

TARGET.write_text(content, encoding='utf-8')
print("✅ 9B classification tuned — much stricter on simple factual questions")
