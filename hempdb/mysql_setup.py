import pymysql

"""
Installs PyMySQL as a drop-in MySQLdb replacement. PyMySQL is pure Python,
so the application needs no MySQL client libraries or build toolchain.
"""
pymysql.version_info = (1, 4, 3, "final", 0)
pymysql.install_as_MySQLdb()
