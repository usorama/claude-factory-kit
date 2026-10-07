# Re-cut these technical phases
The old plan says: first build all database tables, then all APIs, then all UI.
Those are proposed phases, not mandatory order. Replace them with complete paths.
R1: A user adds a shopping-list item and sees it after reload. Start here.
R2: A user marks an existing item bought and the state remains after reload.
R3: A user deletes an item and it remains absent after reload.
Each path crosses UI, API, and persistence, and takes three hours. They share
the list storage engine, whose thin first version belongs in the add-item path.
