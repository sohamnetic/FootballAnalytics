from scripts.identity.identity_manager import IdentityManager

manager = IdentityManager()

print(manager.get_stable_id(
    7,
    1,
    (100, 200),
    (80, 100, 120, 200)
))

print(manager.get_stable_id(
    7,
    2,
    (105, 205),
    (82, 102, 122, 202)
))

print(manager.get_stable_id(
    12,
    2,
    (400, 300),
    (380, 180, 420, 300)
))