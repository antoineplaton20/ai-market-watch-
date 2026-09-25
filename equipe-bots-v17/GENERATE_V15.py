from bot_factory import BotFactory
f=BotFactory()
path=f.export_json()
print(f"catalogue: {path}")
print(f"bots: {len(f.list_bots())}")
