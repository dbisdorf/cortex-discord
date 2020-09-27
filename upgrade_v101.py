import sqlite3

db = sqlite3.connect('cortexpal.db')
db.row_factory = sqlite3.Row
cursor = db.cursor()

cursor.execute(
'CREATE TABLE TEMPTABLE'
'(GUID VARCHAR(32) PRIMARY KEY,'
'SERVER INT NOT NULL,'
'CHANNEL INT NOT NULL,'
'ACTIVITY DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)'
)

cursor.execute('INSERT INTO TEMPTABLE (GUID, SERVER, CHANNEL) SELECT GUID, SERVER, CHANNEL FROM GAME')
cursor.execute('DROP TABLE GAME')

cursor.execute(
'CREATE TABLE IF NOT EXISTS GAME'
'(GUID VARCHAR(32) PRIMARY KEY,'
'SERVER INT NOT NULL,'
'CHANNEL INT NOT NULL,'
'ACTIVITY DATETIME NOT NULL)'
)

cursor.execute('INSERT INTO GAME SELECT GUID, SERVER, CHANNEL, ACTIVITY FROM TEMPTABLE')
cursor.execute('DROP TABLE TEMPTABLE')

db.commit()